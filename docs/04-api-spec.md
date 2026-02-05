# API 仕様（概要）

詳細な定義は `/openapi/openapi.yaml` を参照。

## ベースURL

```
https://api.example.com/v1
```

## 認証

<!-- 認証方式を記述 例: Bearer トークン, API キー -->

## エンドポイント一覧

| メソッド | パス | 説明 |
|---------|------|------|
| POST | /events | イベント送信（単一） |
| POST | /events/batch | イベント一括送信 |
| POST | /identify | ユーザー識別・属性更新 |
| GET | /events | イベント検索・取得 |
| GET | /health | ヘルスチェック |

## 共通レスポンス形式

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

## エラーコード

| コード | HTTP ステータス | 説明 |
|--------|----------------|------|
| INVALID_EVENT | 400 | イベントデータが不正 |
| UNAUTHORIZED | 401 | 認証エラー |
| RATE_LIMITED | 429 | レート制限超過 |
| INTERNAL_ERROR | 500 | サーバー内部エラー |

## レート制限

<!-- レート制限の仕様を記述 -->
