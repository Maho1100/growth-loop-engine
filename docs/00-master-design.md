# Growth Loop Engine — 2週間MVP 設計ドキュメント

| 項目 | 内容 |
|------|------|
| バージョン | MVP v0.1 |
| 想定スプリント | 2週間（10営業日） |
| テーブル数 | 3（users / activities / events） |
| APIエンドポイント数 | 3 |
| イベント種別 | 6種（固定） |

---

## 1. 設計方針

### 1.1 このMVPが解く問い

「ユーザーが学習を続けているか・離脱しかけているか」を判断できる最小のデータ基盤を作る。

### 1.2 設計の3原則

**原則①：記録を落とさない**
行動ログは後から取り直せない。分析やUIは後から足せる。したがって「書き込みの信頼性」に全振りする。

**原則②：テーブルは3つまで**
テーブルが増えるほどJOINが増え、マイグレーションが増え、2週間に収まらなくなる。足りないものは `events.payload`（JSONB）に押し込み、v2で昇格させる。

**原則③：APIは3本まで**
エンドポイントが増えるとテスト・ドキュメント・認証の工数が線形に増える。「書く」「読む（集計）」「読む（デバッグ）」の3本に絞る。

### 1.3 何を捨てたか（v1 → MVP）

| 捨てたもの | 理由 | 復活タイミング |
|---|---|---|
| `contexts` テーブル | 教材/コースの管理はCMSの責務。MVPでは `activities.metadata` に最低限の情報を持たせる | v2：複数教材を横断分析する時点 |
| `streaks_cache` テーブル | ストリークはクエリ時に `events` から計算する。日次アクティブユーザーが1万人を超えるまでは十分高速 | v2：レスポンスが200msを超えた時点 |
| `contexts` の階層構造 | コース→章→セクションの木構造はCMS側で管理すべき | v3：学習パス推薦を実装する時点 |
| ユーザー認証 | MVPでは `external_id` で外部IdPに委任。自前認証は2週間に入らない | v2：マルチテナント対応時 |
| イベントの非同期処理 | キューイング（SQS/RabbitMQ等）はMVPでは過剰。同期書き込みで十分 | v2：秒間100イベントを超えた時点 |
| リアルタイムダッシュボード | WebSocket/SSEは工数が大きい。集計APIをポーリングで代替 | v3 |
| AI連携 | 学習分析AIは `events` テーブルを読めば動く設計にしておくが、MVP期間では接続しない | v2〜v3 |

---

## 2. アーキテクチャ

```
┌──────────────────┐
│  Client (任意)   │
│  ゲーム/研修/LMS │
└────────┬─────────┘
         │ HTTPS
         ▼
┌──────────────────────────────────┐
│  API Server（FastAPI / Python）  │
│                                  │
│  POST /events ─────────────────────→ events テーブルに INSERT
│  GET  /users/{id}/summary ─────────→ events を集計して返す
│  GET  /users/{id}/events ──────────→ events を返す（デバッグ用）
│                                  │
│  バリデーション：                │
│    event_type → 正規表現 + 禁止文字 │
│    payload    → サイズ上限のみ    │
└────────────────┬─────────────────┘
                 │
                 ▼
┌──────────────────────────────────┐
│  PostgreSQL 16                   │
│                                  │
│  ┌────────┐ ┌────────────┐ ┌────────┐
│  │ users  │ │ activities │ │ events │
│  └────────┘ └────────────┘ └────────┘
│       1          1              N
│       └──── 1:N ─┘──── 1:N ────┘
└──────────────────────────────────┘
```

**なぜ FastAPI + PostgreSQL か：**
- FastAPI：Pydanticで型安全なリクエスト/レスポンス定義ができ、OpenAPI YAMLが自動生成される。将来のAI連携もPythonなら追加コストが小さい。
- PostgreSQL：JSONB型で柔軟な `payload` を持てる。`->>`演算子でJSONフィールドを直接集計でき、分析用に別DBを立てる必要がない。

**なぜ単一プロセス・単一DBか：**
2週間でキューやリードレプリカを入れると、インフラ構築だけで1週間消える。日10万イベント規模なら単一構成で十分であり、ボトルネックが見えてから分割するほうが正しい投資になる。

---

## 3. データベース設計

### 3.1 ER図

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

### 3.2 テーブル定義

#### `users` — 学習者

```sql
CREATE TABLE users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id   VARCHAR(255) UNIQUE,
    display_name  VARCHAR(100),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  users IS '学習者。認証は外部IdPに委任し、ここはIDの入れ物に徹する';
COMMENT ON COLUMN users.external_id IS '外部システム（SSO/LMS等）のユーザーID';
```

**設計意図：**
- `external_id` は外部IdPとの紐づけ専用。教育ゲームと企業研修が別の認証基盤を使っていても、このカラムで名寄せできる。
- プロフィール情報（部署・学年・ロール等）はここに持たない。ログ基盤が個人情報を抱えると、GDPR/個人情報保護法への対応コストが跳ね上がる。必要な属性は外部システムから `external_id` で引く。

**捨てたもの：**
- `email`, `role`, `organization_id` などのプロフィールカラム。ログ基盤が知るべきは「誰か」だけであり、「誰であるか」はスコープ外。

---

#### `activities` — 学習単位

```sql
CREATE TABLE activities (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id),
    slug        VARCHAR(100) NOT NULL,
    title       VARCHAR(255),
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, slug)
);

COMMENT ON TABLE  activities IS '学習単位。クイズ1回分、研修1モジュール、ゲーム1ステージ等';
COMMENT ON COLUMN activities.slug IS 'クライアントが付与する識別子（例: quiz-basic-math-01）';
COMMENT ON COLUMN activities.metadata IS '教材バージョン、難易度、カテゴリ等を自由に格納';
```

**設計意図：**
- v1で存在していた `contexts` テーブルを吸収した。`contexts` は「コース全体」を表す抽象度が高いテーブルだったが、MVPでは「ユーザーが今取り組んでいる学習単位」だけ記録できれば十分。
- `UNIQUE(user_id, slug)` により、同一ユーザーが同じ教材に複数回取り組んでも1レコードで管理する。回数や進捗は `events` から計算する。
- `metadata` JSONB に `contexts` が持っていたはずの情報（教材タイプ、コースID、難易度等）を押し込む。構造が固まったらv2でカラムに昇格させる。

**捨てたもの：**
- `type` カラム（'game' / 'training' / 'story' の区分）。MVPでは `metadata.type` で十分。カラムに昇格させるのは、型別のクエリ頻度が高くなってから。
- activities 間の親子関係（コース → 章 → セクション）。階層管理はCMS側に任せ、ログ基盤はフラットなリストで持つ。

---

#### `events` — 行動ログ（設計の中心）

```sql
CREATE TABLE events (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID         NOT NULL REFERENCES users(id),
    activity_id   UUID         REFERENCES activities(id),  -- NULL許容（ログイン等は学習単位に紐づかない）
    event_type    VARCHAR(100) NOT NULL,
    payload       JSONB        NOT NULL DEFAULT '{}',
    occurred_at   TIMESTAMPTZ  NOT NULL,
    received_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 主要クエリパターンに対応するインデックス
CREATE INDEX idx_events_user_occurred
    ON events (user_id, occurred_at DESC);

CREATE INDEX idx_events_user_type
    ON events (user_id, event_type, occurred_at DESC);

CREATE INDEX idx_events_activity
    ON events (activity_id, occurred_at DESC)
    WHERE activity_id IS NOT NULL;

COMMENT ON TABLE  events IS 'Append-only の行動ログ。UPDATE/DELETE は禁止';
COMMENT ON COLUMN events.event_type IS '命名規約: {domain}.{object}.{action}（正規表現でバリデーション）';
COMMENT ON COLUMN events.occurred_at IS 'クライアント側の発生時刻。オフライン学習に対応';
COMMENT ON COLUMN events.received_at IS 'サーバー到着時刻。データ信頼性の監査用';
```

**設計意図の詳細：**

**append-only を強制する理由：**
このテーブルには UPDATE も DELETE も実行しない。理由は3つある。
1. 行動ログを変更すると分析の信頼性が失われる
2. 将来イベントストリーミング（Kafka/Debezium等）に載せる際、append-only なら変更データキャプチャが不要
3. AI連携時に「生データが改竄されていない」ことが前提になる

**`occurred_at` と `received_at` を分離する理由：**
オフライン学習（電車内、山間部の研修施設等）では、イベント発生時刻とサーバー到着時刻がずれる。ストリークや学習時間の計算は `occurred_at` を使い、`received_at` はデータパイプラインの健全性監視に使う。

**`activity_id` がNULL許容の理由：**
`engagement.session_started` や `engagement.goal_set` は特定の学習単位に紐づかない場合がある。NULLを禁止すると「ダミーactivity」を作る必要が生じ、データが汚れる。

**インデックス戦略：**
3つのインデックスは、MVPの3つのAPIが実行するクエリパターンに1対1で対応している。

| インデックス | 対応するAPI / クエリ |
|---|---|
| `idx_events_user_occurred` | `GET /users/{id}/events`（時系列降順） |
| `idx_events_user_type` | `GET /users/{id}/summary`（セッション集計） |
| `idx_events_activity` | activity単位の進捗集計（将来のダッシュボード） |

`WHERE activity_id IS NOT NULL` の部分インデックスにした理由は、NULLのイベント（ログイン等）を含めると無駄にインデックスが肥大化するため。

**捨てたもの：**
- `session_id` カラム：セッションは `session_started` / `session_ended` のペアから計算可能。専用カラムを持つとクライアント側にセッション管理の責務が生じ、実装コストが上がる。
- パーティショニング：月単位のテーブル分割はデータ量が年間5,000万行を超えてから検討する。PostgreSQL 16 のパラレルスキャンがあれば、それ以前は問題にならない。
- GINインデックス（JSONB用）：`payload` の中身を直接検索するクエリはMVPでは存在しない。AI連携時に特定フィールドの検索が頻発したら追加する。

---

### 3.3 MVPで許可するイベント6種

| event_type | payload 例 | 用途 |
|---|---|---|
| `engagement.session_started` | `{"client": "ios", "version": "1.2.0"}` | セッション開始。学習時間の起点 |
| `engagement.session_ended` | `{"reason": "user_exit"}` | セッション終了。滞在時間を計算 |
| `learning.answer_submitted` | `{"question_id": "q-01", "selected": "B", "correct": true, "time_ms": 4200}` | 1問ごとの回答記録。正答率・応答時間の分析 |
| `learning.activity_completed` | `{"score": 85, "time_spent_sec": 320}` | 学習単位の完了。進捗率の分母 |
| `learning.hint_used` | `{"hint_id": "h-03", "hint_number": 2}` | ヒント使用。つまずきポイントの検出 |
| `engagement.goal_set` | `{"goal_type": "daily_minutes", "target": 30}` | 学習目標の設定。モチベーション分析 |

**6種に絞った理由：**
この6種で「いつ・どれくらい・どんな結果で・つまずいたか・目標を持っているか」が分かる。これが「学習を続けているか」を判断する最小セットである。

**捨てたイベント（v2で追加候補）：**

| 候補 | 捨てた理由 |
|---|---|
| `learning.video.played/paused` | 動画教材はMVPスコープ外 |
| `engagement.streak.achieved` | ストリークは派生データであり、クライアントが送るべきではない |
| `game.stage.cleared` | ゲーム固有イベントはゲーム実装と同時に追加する |
| `social.comment.posted` | ソーシャル機能はMVPスコープ外 |

---

### 3.4 マイグレーションSQL（完全版）

```sql
-- Migration: 001_create_tables.sql

BEGIN;

-- 1. users
CREATE TABLE users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id   VARCHAR(255) UNIQUE,
    display_name  VARCHAR(100),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. activities
CREATE TABLE activities (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id),
    slug        VARCHAR(100) NOT NULL,
    title       VARCHAR(255),
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, slug)
);

-- 3. events
CREATE TABLE events (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID         NOT NULL REFERENCES users(id),
    activity_id   UUID         REFERENCES activities(id),
    event_type    VARCHAR(100) NOT NULL,
    payload       JSONB        NOT NULL DEFAULT '{}',
    occurred_at   TIMESTAMPTZ  NOT NULL,
    received_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_user_occurred
    ON events (user_id, occurred_at DESC);

CREATE INDEX idx_events_user_type
    ON events (user_id, event_type, occurred_at DESC);

CREATE INDEX idx_events_activity
    ON events (activity_id, occurred_at DESC)
    WHERE activity_id IS NOT NULL;

COMMIT;
```

---

## 4. event_type バリデーション

### 4.1 方針：ホワイトリストではなく命名規約チェック

ホワイトリスト方式（許可リストに載っていないイベントを拒否）はv1で採用したが、MVPでは**命名規約チェック**に切り替える。

**理由：**
- ホワイトリストはイベント追加のたびにconfig変更＋デプロイが必要
- MVPの6種は固定だが、v2でイベントを追加する際に規約さえ守っていれば自動的に受け入れられるほうが拡張性が高い
- 代わりに、規約に違反するイベントは即座に400エラーで弾く

### 4.2 バリデーションルール

```python
import re

# 命名規約：{domain}.{object}.{action}
# 各パートは英小文字とアンダースコアのみ
EVENT_TYPE_PATTERN = re.compile(
    r'^[a-z][a-z0-9_]*'       # domain: 先頭は英小文字
    r'\.[a-z][a-z0-9_]*'      # object: 先頭は英小文字
    r'\.[a-z][a-z0-9_]*$'     # action: 先頭は英小文字
)

# 禁止文字（SQLインジェクション・パストラバーサル対策）
FORBIDDEN_CHARS = re.compile(r'[;\'"\\/<>{}()\x00-\x1f]')

# 長さ制限
MAX_EVENT_TYPE_LENGTH = 100
MIN_EVENT_TYPE_LENGTH = 5    # 最短でも "a.b.c"

def validate_event_type(event_type: str) -> str | None:
    """
    Returns None if valid, or an error message string if invalid.
    """
    if not isinstance(event_type, str):
        return "event_type must be a string"

    length = len(event_type)
    if length < MIN_EVENT_TYPE_LENGTH:
        return f"event_type too short ({length} < {MIN_EVENT_TYPE_LENGTH})"
    if length > MAX_EVENT_TYPE_LENGTH:
        return f"event_type too long ({length} > {MAX_EVENT_TYPE_LENGTH})"

    if FORBIDDEN_CHARS.search(event_type):
        return "event_type contains forbidden characters"

    if not EVENT_TYPE_PATTERN.match(event_type):
        return (
            "event_type must match pattern: {domain}.{object}.{action} "
            "where each part starts with a-z and contains only a-z, 0-9, _"
        )

    return None  # valid
```

### 4.3 payload バリデーション

MVPでは payload の中身のスキーマチェックは行わない。サイズ上限だけ設ける。

```python
MAX_PAYLOAD_SIZE_BYTES = 8_192  # 8KB

def validate_payload(payload: dict) -> str | None:
    import json
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized.encode('utf-8')) > MAX_PAYLOAD_SIZE_BYTES:
        return f"payload exceeds {MAX_PAYLOAD_SIZE_BYTES} bytes"
    return None
```

**なぜスキーマチェックをしないか：**
イベント種別ごとに payload の構造が異なり、6種すべてのJSON Schemaを定義・保守するコストがMVPに見合わない。壊れたデータが入っても append-only なので上書きされず、集計時にNULL扱いするだけで済む。v2でJSON Schema バリデーションを追加する。

---

## 5. API設計

### 5.1 共通仕様

| 項目 | 仕様 |
|---|---|
| ベースURL | `https://api.example.com/v1` |
| Content-Type | `application/json` |
| 認証 | MVPでは Bearer Token（静的トークン）。v2でOAuth2 |
| エラー形式 | RFC 7807 Problem Details |
| タイムゾーン | すべてUTC（ISO 8601） |

エラーレスポンスの形式：

```json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "event_type must match pattern: {domain}.{object}.{action}",
  "instance": "/v1/events"
}
```

---

### 5.2 POST /events — イベント記録

**責務：** 行動ログをバッチで受け取り、バリデーション後にDBに書き込む。

#### リクエスト

```
POST /v1/events
Content-Type: application/json
Authorization: Bearer {token}
```

```json
{
  "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "events": [
    {
      "event_type": "engagement.session_started",
      "payload": {
        "client": "ios",
        "version": "1.2.0"
      },
      "activity_id": null,
      "occurred_at": "2026-02-01T09:00:00Z"
    },
    {
      "event_type": "learning.answer_submitted",
      "payload": {
        "question_id": "q-01",
        "selected": "B",
        "correct": true,
        "time_ms": 4200
      },
      "activity_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "occurred_at": "2026-02-01T09:05:30Z"
    }
  ]
}
```

#### リクエストスキーマ（Pydantic）

```python
from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime

class EventIn(BaseModel):
    event_type: str = Field(
        ...,
        min_length=5,
        max_length=100,
        examples=["learning.answer_submitted"]
    )
    payload: dict = Field(default_factory=dict)
    activity_id: UUID | None = None
    occurred_at: datetime | None = None  # 省略時はサーバー時刻

    @field_validator('event_type')
    @classmethod
    def check_event_type(cls, v: str) -> str:
        error = validate_event_type(v)
        if error:
            raise ValueError(error)
        return v

    @field_validator('payload')
    @classmethod
    def check_payload_size(cls, v: dict) -> dict:
        error = validate_payload(v)
        if error:
            raise ValueError(error)
        return v


class EventBatchIn(BaseModel):
    user_id: UUID
    events: list[EventIn] = Field(
        ...,
        min_length=1,
        max_length=100
    )


class EventOut(BaseModel):
    id: UUID
    received_at: datetime


class EventBatchOut(BaseModel):
    accepted: int
    events: list[EventOut]
```

#### レスポンス（成功：201 Created）

```json
{
  "accepted": 2,
  "events": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "received_at": "2026-02-01T09:00:01.234Z"
    },
    {
      "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "received_at": "2026-02-01T09:00:01.235Z"
    }
  ]
}
```

#### エラーレスポンス例

**400 Bad Request（バリデーションエラー）：**

```json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "events[1].event_type: event_type must match pattern: {domain}.{object}.{action}",
  "instance": "/v1/events"
}
```

**404 Not Found（ユーザーが存在しない）：**

```json
{
  "type": "https://api.example.com/errors/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "User f47ac10b-58cc-4372-a567-0e02b2c3d479 not found",
  "instance": "/v1/events"
}
```

#### 実装上の判断

**バッチ全体をアトミックに書き込む理由：**
100件中1件がバリデーションエラーなら100件全部を拒否する。部分成功を許すと、クライアント側のリトライロジックが複雑になる（「どの件が成功してどの件が失敗したか」の追跡が必要になる）。MVPでは「全成功 or 全失敗」がもっともシンプル。

**`occurred_at` 省略時の挙動：**
省略時はサーバー時刻（`now()`）を使う。オフライン対応を活かしたいクライアントは必ず `occurred_at` を送る。MVPではクライアント時刻のドリフト検証（未来日付の拒否等）は行わない。v2で `received_at - occurred_at > 24h` のアラートを入れる。

---

### 5.3 GET /users/{id}/summary — 学習統計

**責務：** ストリーク・週間学習頻度・平均セッション時間を返す。

#### リクエスト

```
GET /v1/users/f47ac10b-58cc-4372-a567-0e02b2c3d479/summary
Authorization: Bearer {token}
```

#### レスポンス（200 OK）

```json
{
  "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "computed_at": "2026-02-05T12:00:00Z",
  "streak": {
    "current_days": 5,
    "longest_days": 12,
    "last_active_date": "2026-02-05"
  },
  "weekly_frequency": {
    "weeks_counted": 4,
    "avg_days_per_week": 4.5,
    "this_week_days": 3
  },
  "session": {
    "avg_duration_sec": 1080,
    "total_sessions_30d": 22
  }
}
```

#### 集計SQLの設計意図

**ストリーク計算：**

```sql
-- ユーザーのアクティブ日を降順に列挙し、連続性を判定する
WITH active_days AS (
    SELECT DISTINCT (occurred_at AT TIME ZONE 'UTC')::date AS d
    FROM events
    WHERE user_id = $1
    ORDER BY d DESC
),
numbered AS (
    SELECT d,
           d - (ROW_NUMBER() OVER (ORDER BY d DESC))::int AS grp
    FROM active_days
)
SELECT
    COUNT(*) AS current_streak,
    MIN(d) AS streak_start
FROM numbered
WHERE grp = (SELECT grp FROM numbered LIMIT 1);
```

**なぜキャッシュテーブルではなくクエリ時計算か：**
- MVPのユーザー規模（〜数千人）では、インデックスが効いた上記クエリは10ms以下で返る
- キャッシュテーブルを持つと「キャッシュの更新タイミング」「不整合時のリカバリ」という新しい問題が生まれる
- v2でレスポンスが200msを超えたら `streaks_cache` を復活させる

**セッション時間の計算：**

```sql
-- session_started と session_ended のペアからセッション時間を計算
WITH sessions AS (
    SELECT
        occurred_at AS started_at,
        LEAD(occurred_at) OVER (ORDER BY occurred_at) AS ended_at,
        event_type
    FROM events
    WHERE user_id = $1
      AND event_type IN ('engagement.session_started', 'engagement.session_ended')
      AND occurred_at >= now() - INTERVAL '30 days'
    ORDER BY occurred_at
)
SELECT
    AVG(EXTRACT(EPOCH FROM (ended_at - started_at)))::int AS avg_duration_sec,
    COUNT(*) AS total_sessions
FROM sessions
WHERE event_type = 'engagement.session_started'
  AND ended_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (ended_at - started_at)) BETWEEN 10 AND 14400;
  -- 10秒未満は誤操作、4時間超はセッション切れ忘れとして除外
```

**セッション時間の10秒〜4時間フィルタの理由：**
ゲームや研修アプリでは「起動して即閉じた」「閉じ忘れてバックグラウンドで放置」が頻繁に起きる。このノイズを集計に含めると平均値が無意味になるため、合理的な範囲でフィルタする。閾値はv2でconfigに切り出す。

---

### 5.4 GET /users/{id}/events — イベント履歴（デバッグ用）

**責務：** 特定ユーザーのイベント生データを返す。デバッグ・CS対応用。

#### リクエスト

```
GET /v1/users/f47ac10b-58cc-4372-a567-0e02b2c3d479/events?limit=20&offset=0&event_type=learning.answer_submitted
Authorization: Bearer {token}
```

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `limit` | int | 50 | 最大100 |
| `offset` | int | 0 | ページネーション用 |
| `event_type` | string | (なし) | 任意フィルタ |
| `since` | datetime | (なし) | この時刻以降のみ |
| `until` | datetime | (なし) | この時刻以前のみ |

#### レスポンス（200 OK）

```json
{
  "user_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "total": 142,
  "limit": 20,
  "offset": 0,
  "events": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "event_type": "learning.answer_submitted",
      "payload": {
        "question_id": "q-01",
        "selected": "B",
        "correct": true,
        "time_ms": 4200
      },
      "activity_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "occurred_at": "2026-02-01T09:05:30Z",
      "received_at": "2026-02-01T09:05:31.234Z"
    }
  ]
}
```

**なぜ offset ベースのページネーションか：**
cursor ベース（`after=<last_id>`）のほうがパフォーマンスは良いが、デバッグ用途では「3ページ目を直接開く」ことがあるため offset が便利。データ量が10万行を超えたらcursorに移行する。

---

## 6. OpenAPI 3.0 仕様（YAML）

```yaml
openapi: "3.0.3"
info:
  title: Growth Loop Engine API
  version: 0.1.0
  description: |
    学習継続を支えるための行動ログ基盤（MVP）。
    教育ゲーム・企業研修・ストーリー教材に転用可能な設計。
servers:
  - url: https://api.example.com/v1
    description: Production
  - url: http://localhost:8000/v1
    description: Local development

paths:
  /events:
    post:
      operationId: createEvents
      summary: イベント記録（バッチ対応）
      description: |
        最大100件のイベントをバッチで記録する。
        全件バリデーション成功時のみ書き込み（アトミック）。
      tags: [Events]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/EventBatchIn'
            example:
              user_id: "f47ac10b-58cc-4372-a567-0e02b2c3d479"
              events:
                - event_type: "engagement.session_started"
                  payload:
                    client: "ios"
                    version: "1.2.0"
                  occurred_at: "2026-02-01T09:00:00Z"
                - event_type: "learning.answer_submitted"
                  payload:
                    question_id: "q-01"
                    selected: "B"
                    correct: true
                    time_ms: 4200
                  activity_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                  occurred_at: "2026-02-01T09:05:30Z"
      responses:
        "201":
          description: イベント記録成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/EventBatchOut'
              example:
                accepted: 2
                events:
                  - id: "550e8400-e29b-41d4-a716-446655440000"
                    received_at: "2026-02-01T09:00:01.234Z"
                  - id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
                    received_at: "2026-02-01T09:00:01.235Z"
        "400":
          $ref: '#/components/responses/ValidationError'
        "404":
          $ref: '#/components/responses/NotFound'

  /users/{user_id}/summary:
    get:
      operationId: getUserSummary
      summary: 学習統計
      description: |
        ストリーク（連続学習日数）、週間学習頻度、
        直近30日の平均セッション時間を返す。
        キャッシュなし、リクエスト時に都度計算。
      tags: [Users]
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: 統計情報
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UserSummary'
              example:
                user_id: "f47ac10b-58cc-4372-a567-0e02b2c3d479"
                computed_at: "2026-02-05T12:00:00Z"
                streak:
                  current_days: 5
                  longest_days: 12
                  last_active_date: "2026-02-05"
                weekly_frequency:
                  weeks_counted: 4
                  avg_days_per_week: 4.5
                  this_week_days: 3
                session:
                  avg_duration_sec: 1080
                  total_sessions_30d: 22
        "404":
          $ref: '#/components/responses/NotFound'

  /users/{user_id}/events:
    get:
      operationId: getUserEvents
      summary: イベント履歴（デバッグ用）
      description: |
        特定ユーザーのイベント生データを時系列降順で返す。
        CS対応・デバッグ用途を想定。
      tags: [Users]
      parameters:
        - name: user_id
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: limit
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 50
        - name: offset
          in: query
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: event_type
          in: query
          schema:
            type: string
            maxLength: 100
        - name: since
          in: query
          schema:
            type: string
            format: date-time
        - name: until
          in: query
          schema:
            type: string
            format: date-time
      responses:
        "200":
          description: イベント一覧
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/EventList'
              example:
                user_id: "f47ac10b-58cc-4372-a567-0e02b2c3d479"
                total: 142
                limit: 20
                offset: 0
                events:
                  - id: "550e8400-e29b-41d4-a716-446655440000"
                    event_type: "learning.answer_submitted"
                    payload:
                      question_id: "q-01"
                      selected: "B"
                      correct: true
                      time_ms: 4200
                    activity_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                    occurred_at: "2026-02-01T09:05:30Z"
                    received_at: "2026-02-01T09:05:31.234Z"
        "404":
          $ref: '#/components/responses/NotFound'

components:
  schemas:
    EventIn:
      type: object
      required: [event_type]
      properties:
        event_type:
          type: string
          minLength: 5
          maxLength: 100
          pattern: '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'
          description: "命名規約: {domain}.{object}.{action}"
        payload:
          type: object
          default: {}
          description: "最大8KB。イベント種別ごとの自由データ"
        activity_id:
          type: string
          format: uuid
          nullable: true
        occurred_at:
          type: string
          format: date-time
          nullable: true
          description: "省略時はサーバー時刻"

    EventBatchIn:
      type: object
      required: [user_id, events]
      properties:
        user_id:
          type: string
          format: uuid
        events:
          type: array
          items:
            $ref: '#/components/schemas/EventIn'
          minItems: 1
          maxItems: 100

    EventOut:
      type: object
      properties:
        id:
          type: string
          format: uuid
        received_at:
          type: string
          format: date-time

    EventBatchOut:
      type: object
      properties:
        accepted:
          type: integer
        events:
          type: array
          items:
            $ref: '#/components/schemas/EventOut'

    EventDetail:
      type: object
      properties:
        id:
          type: string
          format: uuid
        event_type:
          type: string
        payload:
          type: object
        activity_id:
          type: string
          format: uuid
          nullable: true
        occurred_at:
          type: string
          format: date-time
        received_at:
          type: string
          format: date-time

    EventList:
      type: object
      properties:
        user_id:
          type: string
          format: uuid
        total:
          type: integer
        limit:
          type: integer
        offset:
          type: integer
        events:
          type: array
          items:
            $ref: '#/components/schemas/EventDetail'

    StreakInfo:
      type: object
      properties:
        current_days:
          type: integer
          description: "現在の連続学習日数"
        longest_days:
          type: integer
          description: "最長の連続学習日数"
        last_active_date:
          type: string
          format: date
          description: "最終アクティブ日"

    WeeklyFrequency:
      type: object
      properties:
        weeks_counted:
          type: integer
          description: "集計対象の週数（直近4週）"
        avg_days_per_week:
          type: number
          format: float
          description: "週あたりの平均学習日数"
        this_week_days:
          type: integer
          description: "今週の学習日数"

    SessionStats:
      type: object
      properties:
        avg_duration_sec:
          type: integer
          description: "直近30日の平均セッション時間（秒）"
        total_sessions_30d:
          type: integer
          description: "直近30日のセッション数"

    UserSummary:
      type: object
      properties:
        user_id:
          type: string
          format: uuid
        computed_at:
          type: string
          format: date-time
        streak:
          $ref: '#/components/schemas/StreakInfo'
        weekly_frequency:
          $ref: '#/components/schemas/WeeklyFrequency'
        session:
          $ref: '#/components/schemas/SessionStats'

    ProblemDetail:
      type: object
      properties:
        type:
          type: string
          format: uri
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        instance:
          type: string

  responses:
    ValidationError:
      description: バリデーションエラー
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
          example:
            type: "https://api.example.com/errors/validation"
            title: "Validation Error"
            status: 400
            detail: "events[1].event_type: event_type must match pattern: {domain}.{object}.{action}"
            instance: "/v1/events"
    NotFound:
      description: リソースが見つからない
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
          example:
            type: "https://api.example.com/errors/not-found"
            title: "Not Found"
            status: 404
            detail: "User f47ac10b-58cc-4372-a567-0e02b2c3d479 not found"
            instance: "/v1/users/f47ac10b-58cc-4372-a567-0e02b2c3d479/summary"

  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer

security:
  - BearerAuth: []
```

---

## 7. 将来の拡張パス

```
MVP (2週間)                  v2 (1-2ヶ月後)                  v3 (将来)
──────────────             ──────────────────             ──────────────

3テーブル               →  contexts テーブル復活         →  コース横断分析
                           streaks_cache 復活                学習パス推薦

6イベント種別           →  動画/ゲーム/ソーシャル追加    →  カスタムイベント定義UI
                           payload JSON Schema導入

クエリ時計算            →  マテリアライズドビュー        →  リアルタイム集計
                           or キャッシュテーブル             (ClickHouse連携)

命名規約チェック        →  規約チェック + ホワイトリスト  →  イベントカタログUI
                           の二段構え

offset ページネーション →  cursor ページネーション        →  全文検索(Elasticsearch)

同期書き込み            →  非同期キュー                  →  イベントストリーミング
                           (SQS/RabbitMQ)                   (Kafka)

単一API + PostgreSQL    →  読み取りレプリカ              →  CQRS + Event Sourcing
```

### MVPが守っている拡張点

| 拡張点 | MVPでの対応 |
|---|---|
| events が append-only | UPDATE/DELETE を禁止することで、将来どんなストリーミング基盤にもそのまま接続できる |
| event_type の命名規約 | `{domain}.{object}.{action}` の3段構造により、AI特徴量抽出時にドメイン分類が自動化できる |
| payload が JSONB | 構造が固まったカラムだけを v2 でテーブルに昇格させればよく、既存データの移行が不要 |
| occurred_at / received_at の分離 | オフライン対応とデータパイプライン監視の両方が最初から可能 |
| activity_id の NULL 許容 | 学習単位に紐づかないイベントを自然に表現でき、将来の contexts 復活時にも設計変更が不要 |

---

## 8. 2週間スプリント計画

| 日 | タスク | 完了条件 |
|---|---|---|
| Day 1 | DB設計FIX・マイグレーション実行・FastAPIプロジェクト初期化 | テーブル3つが存在し、空のAPIが起動する |
| Day 2-3 | `POST /events` 実装（バリデーション・バッチINSERT） | 100件バッチが1秒以内に書き込める |
| Day 4-5 | `GET /users/{id}/events` 実装（フィルタ・ページネーション） | event_type・日時フィルタが動作する |
| Day 6-7 | `GET /users/{id}/summary` 実装（ストリーク・頻度・セッション計算） | テストデータで正しい値が返る |
| Day 8 | エラーハンドリング統一（RFC 7807）・ロギング整備 | 全エラーがProblemDetail形式で返る |
| Day 9 | テスト（pytest：正常系・異常系・境界値） | カバレッジ80%以上 |
| Day 10 | OpenAPI YAML 最終確認・README・デプロイ | ドキュメントが最新で本番稼働可能 |
