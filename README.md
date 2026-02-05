# Growth Loop Engine

学習継続を支えるための行動ログ基盤（MVP）。
教育ゲーム・企業研修・ストーリー教材に転用可能な設計。

## 概要

「ユーザーが学習を続けているか・離脱しかけているか」を判断できる最小のデータ基盤。

| 項目 | 内容 |
|------|------|
| テーブル数 | 3（users / activities / events） |
| APIエンドポイント数 | 3 |
| イベント種別 | 6種（固定） |
| 技術スタック | FastAPI + PostgreSQL 16 |

## ディレクトリ構成

```
/docs
  00-master-design.md      正の設計書（この文書が唯一の権威）
  01-mvp-requirements.md   MVP要件定義
  02-event-taxonomy.md     イベント分類体系（6種 + バリデーション方針）
  03-data-model.md         データモデル設計（3テーブル）
  04-api-spec.md           API仕様概要（3エンドポイント）
/db
  schema.sql               PostgreSQL 16 スキーマ
/openapi
  openapi.yaml             OpenAPI 3.0.3 定義
```

## API

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/v1/events` | イベント記録（バッチ対応） |
| GET | `/v1/users/{user_id}/summary` | 学習統計 |
| GET | `/v1/users/{user_id}/events` | イベント履歴 |

## セットアップ

TODO

## 開発

TODO

## ライセンス

TODO
