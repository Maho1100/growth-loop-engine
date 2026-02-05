# API 仕様（概要）

詳細な定義は `/openapi/openapi.yaml` を参照。

## 共通仕様

| 項目 | 仕様 |
|---|---|
| ベースURL | `https://api.example.com/v1` |
| Content-Type | `application/json` |
| 認証 | Bearer Token（MVPでは静的トークン。v2でOAuth2） |
| エラー形式 | RFC 7807 Problem Details |
| タイムゾーン | すべてUTC（ISO 8601） |

## エンドポイント一覧（3本）

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/v1/events` | イベント記録（バッチ対応、最大100件、アトミック） |
| GET | `/v1/users/{user_id}/summary` | 学習統計（ストリーク・週間頻度・セッション時間） |
| GET | `/v1/users/{user_id}/events` | イベント履歴（デバッグ・CS対応用） |

## POST /v1/events — イベント記録

最大100件のイベントをバッチで受け取り、全件バリデーション成功時のみアトミックに書き込む。

- 成功: `201 Created`
- バリデーションエラー: `400 Bad Request`
- ユーザー不在: `404 Not Found`

**バッチ全体をアトミックに書き込む理由：**
部分成功を許すとクライアント側のリトライロジックが複雑になる。MVPでは「全成功 or 全失敗」がもっともシンプル。

## GET /v1/users/{user_id}/summary — 学習統計

ストリーク（連続学習日数）、週間学習頻度、直近30日の平均セッション時間を返す。キャッシュなし、リクエスト時に都度計算。

- 成功: `200 OK`
- ユーザー不在: `404 Not Found`

## GET /v1/users/{user_id}/events — イベント履歴

特定ユーザーのイベント生データを時系列降順で返す。

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `limit` | int | 50 | 最大100 |
| `offset` | int | 0 | ページネーション用 |
| `event_type` | string | (なし) | 任意フィルタ |
| `since` | datetime | (なし) | この時刻以降のみ |
| `until` | datetime | (なし) | この時刻以前のみ |

- 成功: `200 OK`
- ユーザー不在: `404 Not Found`

## エラーレスポンス形式（RFC 7807）

```json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "event_type must match pattern: {domain}.{object}.{action}",
  "instance": "/v1/events"
}
```
