# データモデル設計

## ER図

```
┌─────────────────┐       ┌──────────────────────┐       ┌─────────────────────────────┐
│     users        │       │     activities        │       │          events              │
├─────────────────┤       ├──────────────────────┤       ├─────────────────────────────┤
│ id          UUID PK      │ id          UUID PK   │       │ id            UUID PK        │
│ external_id VARCHAR UK   │ user_id     UUID FK ──┤───┐   │ user_id       UUID FK ───────┤──→ users
│ display_name VARCHAR     │ slug        VARCHAR UK│   │   │ activity_id   UUID FK ───────┤──→ activities (nullable)
│ created_at  TIMESTAMPTZ  │ title       VARCHAR   │   │   │ event_type    VARCHAR(100)   │
│ updated_at  TIMESTAMPTZ  │ metadata    JSONB     │   │   │ payload       JSONB          │
└─────────────────┘       │ created_at  TIMESTAMPTZ│   │   │ occurred_at   TIMESTAMPTZ    │
                          │ updated_at  TIMESTAMPTZ│   │   │ received_at   TIMESTAMPTZ    │
                          └──────────────────────┘   │   └─────────────────────────────┘
                                                     │         ▲
                                       users 1:N ────┘         │
                                       activities 1:N ─────────┘
```

## テーブル一覧

| テーブル名 | 説明 |
|-----------|------|
| users | 学習者。認証は外部IdPに委任し、IDの入れ物に徹する |
| activities | 学習単位。クイズ1回分、研修1モジュール、ゲーム1ステージ等 |
| events | Append-only の行動ログ。UPDATE/DELETE は禁止 |

## テーブル詳細

### users — 学習者

| カラム | 型 | NULL | 説明 |
|--------|---|------|------|
| id | UUID | NOT NULL | 主キー（`gen_random_uuid()`） |
| external_id | VARCHAR(255) | NULL | 外部システム（SSO/LMS等）のユーザーID。UNIQUE |
| display_name | VARCHAR(100) | NULL | 表示名 |
| created_at | TIMESTAMPTZ | NOT NULL | 作成日時 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新日時 |

**設計意図：**
- `external_id` は外部IdPとの紐づけ専用。教育ゲームと企業研修が別の認証基盤を使っていても名寄せできる
- プロフィール情報（部署・学年・ロール等）はここに持たない。ログ基盤が個人情報を抱えるとGDPR/個人情報保護法への対応コストが跳ね上がる

### activities — 学習単位

| カラム | 型 | NULL | 説明 |
|--------|---|------|------|
| id | UUID | NOT NULL | 主キー（`gen_random_uuid()`） |
| user_id | UUID | NOT NULL | FK → users(id) |
| slug | VARCHAR(100) | NOT NULL | クライアントが付与する識別子。UNIQUE(user_id, slug) |
| title | VARCHAR(255) | NULL | 学習単位のタイトル |
| metadata | JSONB | NOT NULL | 教材バージョン、難易度、カテゴリ等を自由に格納 |
| created_at | TIMESTAMPTZ | NOT NULL | 作成日時 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新日時 |

**設計意図：**
- v1の `contexts` テーブルを吸収。MVPでは「ユーザーが今取り組んでいる学習単位」だけ記録できれば十分
- `UNIQUE(user_id, slug)` により、同一ユーザーが同じ教材に複数回取り組んでも1レコードで管理。回数や進捗は `events` から計算する
- `metadata` JSONB に教材タイプ、コースID、難易度等を押し込む。構造が固まったらv2でカラムに昇格

### events — 行動ログ（設計の中心）

| カラム | 型 | NULL | 説明 |
|--------|---|------|------|
| id | UUID | NOT NULL | 主キー（`gen_random_uuid()`） |
| user_id | UUID | NOT NULL | FK → users(id) |
| activity_id | UUID | NULL | FK → activities(id)。学習単位に紐づかないイベントはNULL |
| event_type | VARCHAR(100) | NOT NULL | `{domain}.{object}.{action}` 形式 |
| payload | JSONB | NOT NULL | イベント固有データ（最大8KB） |
| occurred_at | TIMESTAMPTZ | NOT NULL | クライアント側の発生時刻 |
| received_at | TIMESTAMPTZ | NOT NULL | サーバー到着時刻 |

**設計意図：**
- **append-only** — UPDATE/DELETEを禁止。行動ログの信頼性を保証し、将来のイベントストリーミング対応を容易にする
- **occurred_at / received_at の分離** — オフライン学習（電車内、山間部の研修施設等）でのタイムラグに対応
- **activity_id がNULL許容** — `engagement.session_started` 等は特定の学習単位に紐づかない

## インデックス戦略

| インデックス | 対応するAPI / クエリ |
|---|---|
| `idx_events_user_occurred (user_id, occurred_at DESC)` | `GET /users/{id}/events`（時系列降順） |
| `idx_events_user_type (user_id, event_type, occurred_at DESC)` | `GET /users/{id}/summary`（セッション集計） |
| `idx_events_activity (activity_id, occurred_at DESC) WHERE activity_id IS NOT NULL` | activity単位の進捗集計（将来のダッシュボード） |

`idx_events_activity` を部分インデックスにした理由：NULLのイベント（ログイン等）を含めると無駄にインデックスが肥大化するため。
