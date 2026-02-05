# イベント分類体系（Event Taxonomy）

## 命名規約

`{domain}.{object}.{action}` の3段構造。各パートは英小文字・数字・アンダースコアのみ。

```
例: engagement.session_started, learning.answer_submitted
```

## MVPで許可するイベント6種

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

## v2以降の追加候補

| 候補 | 捨てた理由 |
|---|---|
| `learning.video.played/paused` | 動画教材はMVPスコープ外 |
| `engagement.streak.achieved` | ストリークは派生データであり、クライアントが送るべきではない |
| `game.stage.cleared` | ゲーム固有イベントはゲーム実装と同時に追加する |
| `social.comment.posted` | ソーシャル機能はMVPスコープ外 |

## event_type バリデーション方針

ホワイトリスト方式ではなく **命名規約チェック** を採用する。規約に違反するイベントは即座に400エラーで弾く。

### バリデーションルール

| ルール | 内容 |
|--------|------|
| 正規表現 | `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` |
| 最小長 | 5文字（最短で `a.b.c`） |
| 最大長 | 100文字 |
| 禁止文字 | `; ' " \ / < > { } ( )` および制御文字 |

**なぜホワイトリストではないか：**
- ホワイトリストはイベント追加のたびにconfig変更＋デプロイが必要
- MVPの6種は固定だが、v2でイベントを追加する際に規約さえ守っていれば自動的に受け入れられるほうが拡張性が高い
- 代わりに、規約に違反するイベントは即座に400エラーで弾く

## payload バリデーション

MVPでは payload の中身のスキーマチェックは行わない。サイズ上限のみ設ける。

| ルール | 内容 |
|--------|------|
| 最大サイズ | 8KB（8,192バイト） |
| スキーマチェック | なし（v2でJSON Schema導入予定） |

## 共通フィールド

すべてのイベントに付与されるフィールド（events テーブルのカラムとして格納）。

| フィールド名 | 型 | 説明 |
|-------------|---|------|
| id | UUID | イベント一意識別子 |
| user_id | UUID | ユーザー識別子（必須） |
| activity_id | UUID | 学習単位の識別子（NULL許容） |
| event_type | VARCHAR(100) | イベント種別（命名規約に準拠） |
| payload | JSONB | イベント固有のプロパティ |
| occurred_at | TIMESTAMPTZ | クライアント側の発生時刻 |
| received_at | TIMESTAMPTZ | サーバー到着時刻 |
