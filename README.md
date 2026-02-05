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


🚀 Quick Start（ローカルでの再現手順）

このプロジェクトは FastAPI + PostgreSQL + Docker を用いた
学習・行動ログ基盤（Growth Loop Engine）の MVP 実装です。

以下の手順で、誰でもローカル環境で API を起動し、
イベント記録 → 集計結果取得までを再現できます。

0. 前提条件

Windows / macOS / Linux

Docker Desktop（PostgreSQL 用）

Python 3.10+

Git

1. リポジトリをクローン
git clone <this-repository>
git clone https://github.com/Maho1100/growth-loop-engine.git
cd growth-loop-engine

2. PostgreSQL を起動（Docker）
docker compose up -d


起動確認：

docker ps


postgres:16 コンテナが Up になっていればOKです。

3. データベース初期化（スキーマ適用）
$cid = docker ps -q --filter "name=growth-loop-engine-db-1"
Get-Content .\db\schema.sql | docker exec -i $cid psql -U gle -d growth_loop


テーブル確認：

docker exec -it $cid psql -U gle -d growth_loop -c "\dt"

4. Python 仮想環境のセットアップ
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

5. FastAPI サーバー起動
$env:DATABASE_URL="postgresql://gle:gle@localhost:5432/growth_loop"
uvicorn app.main:app --reload


起動後：

http://127.0.0.1:8000

6. テスト用ユーザーを作成（DB直操作）
INSERT INTO users (id, external_id, display_name)
VALUES (gen_random_uuid(), 'manual-test-001', 'Manual Test User');


ユーザーIDを取得：

SELECT id FROM users;

7. イベントを POST（PowerShell）
$userId = "<取得したUUID>"
$now = (Get-Date).ToUniversalTime().ToString("o")

curl -Method Post "http://127.0.0.1:8000/v1/events" `
  -ContentType "application/json" `
  -Body (@{
    user_id = $userId
    events = @(@{
      event_type = "engagement.session.started"
      payload = @{ client = "web" }
      occurred_at = $now
    })
  } | ConvertTo-Json -Depth 10)


成功時：

{
  "accepted": 1,
  "events": [
    {
      "id": "...",
      "received_at": "..."
    }
  ]
}

8. 集計結果を取得
curl "http://127.0.0.1:8000/v1/users/$userId/summary"


レスポンス例：

{
  "user_id": "...",
  "computed_at": "...",
  "streak": {
    "current_days": 1,
    "longest_days": 1,
    "last_active_date": "2026-02-05"
  },
  "weekly_frequency": {
    "weeks_counted": 1,
    "avg_days_per_week": 1,
    "this_week_days": 1
  }
}

9. テスト実行（結合テスト）
python -m pytest -v


結果：

3 passed in X.XXs

🧠 設計方針（要点）

イベントログ中心設計（append-only）

集計は後段で計算（AI/分析基盤へ拡張可能）

docs/00-master-design.md を唯一の正とする

MVPでは「記録の完全性」を最優先