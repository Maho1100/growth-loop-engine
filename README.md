# Growth Loop Engine

> This repository demonstrates how to design and implement
> an event-log–centric backend with reproducible local setup
> and end-to-end integration tests.

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

## 🚀 Quick Start（ローカルでの再現手順）

> **Note:** 本手順は Windows 11 (PowerShell) で検証済みです。
> macOS / Linux をお使いの場合は、PowerShell 固有の構文を適宜読み替えてください
>（例: `$env:VAR="val"` → `export VAR=val`、`Get-Content` → `cat`）。

このプロジェクトは FastAPI + PostgreSQL + Docker を用いた
学習・行動ログ基盤（Growth Loop Engine）の MVP 実装です。

以下の手順で、誰でもローカル環境で API を起動し、
イベント記録 → 集計結果取得までを再現できます。

### 0. 前提条件

- Windows / macOS / Linux
- Docker Desktop（PostgreSQL 用）
- Python 3.10+
- Git

### 1. リポジトリをクローン

PowerShell を開き、ホームディレクトリ（`C:\Users\<ユーザー名>`）で実行します：

```bash
git clone https://github.com/Maho1100/growth-loop-engine.git
cd growth-loop-engine
```

> クローン先は `~/growth-loop-engine` になります。以降の手順はこのフォルダ内で実行します。

### 2. PostgreSQL を起動（Docker）

```bash
docker compose up -d
```

起動確認：

```bash
docker ps
```

`postgres:16` コンテナが **Up** になっていればOKです。

### 3. データベース初期化（スキーマ適用）

```powershell
$cid = docker ps -q --filter "name=growth-loop-engine-db-1"
Get-Content .\db\schema.sql | docker exec -i $cid psql -U gle -d growth_loop
```

テーブル確認：

```powershell
docker exec -it $cid psql -U gle -d growth_loop -c "\dt"
```

### 4. Python 仮想環境のセットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5. FastAPI サーバー起動

```powershell
$env:DATABASE_URL="postgresql://gle:gle@localhost:5432/growth_loop"
uvicorn app.main:app --reload
```

起動後、以下にアクセスできます：

```
http://127.0.0.1:8000
```

> ルートパス `/` には `{"detail":"Not Found"}` が返りますが、これは正常です。
> API ドキュメントは [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) で確認できます。

### 6. テスト用ユーザーを作成（DB 直操作）

> **Note:** uvicorn を動かしているターミナルはそのまま残し、
> **新しい PowerShell ウィンドウ**を開いて以下を実行してください。
> `$cid` はターミナルごとに独立なので、再度セットが必要です。

```powershell
cd ~\growth-loop-engine
$cid = docker ps -q --filter "name=growth-loop-engine-db-1"
docker exec -it $cid psql -U gle -d growth_loop
```

`growth_loop=#` プロンプトが表示されたら、以下の SQL を実行します：

```sql
-- psql コンソール内で実行
INSERT INTO users (id, external_id, display_name)
VALUES (gen_random_uuid(), 'manual-test-001', 'Manual Test User');
```

ユーザー ID を取得：

```sql
SELECT id FROM users;
```

取得した UUID をメモしたら、psql から抜けます：

```sql
\q
```

### 7. イベントを POST（PowerShell）

> **Note:** ここからは **PowerShell**（`PS C:\...>` プロンプト）で実行します。
> `growth_loop=#` のままの場合は、`\q` で psql を抜けてください。

```powershell
$userId = "<取得したUUID>"
$now = (Get-Date).ToUniversalTime().ToString("o")

Invoke-RestMethod -Method Post "http://127.0.0.1:8000/v1/events" `
  -ContentType "application/json" `
  -Body (@{
    user_id = $userId
    events = @(@{
      event_type = "engagement.session.started"
      payload = @{ client = "web" }
      occurred_at = $now
    })
  } | ConvertTo-Json -Depth 10)
```

成功時のレスポンス：

```json
{
  "accepted": 1,
  "events": [
    {
      "id": "...",
      "received_at": "..."
    }
  ]
}
```

### 8. 集計結果を取得

```powershell
curl "http://127.0.0.1:8000/v1/users/$userId/summary"
```

レスポンス例：

```json
{
  "user_id": "...",
  "computed_at": "...",
  "streak": {
    "current_days": 1,
    "longest_days": 1,
    "last_active_date": "YYYY-MM-DD"
  },
  "weekly_frequency": {
    "weeks_counted": 1,
    "avg_days_per_week": 1,
    "this_week_days": 1
  },
  "session": {
    "avg_duration_sec": 0,
    "total_sessions_30d": 1
  }
}
```

### 9. テスト実行（結合テスト）

> **Note:** 仮想環境が有効になっていることを確認してください。
> プロンプトの先頭に `(.venv)` が表示されていない場合は、以下を先に実行します。

```powershell
cd ~\growth-loop-engine
.\.venv\Scripts\Activate.ps1
```

テスト用データベースを作成し、スキーマを適用します（初回のみ）：

```powershell
$cid = docker ps -q --filter "name=growth-loop-engine-db-1"
docker exec -it $cid psql -U gle -d growth_loop -c "CREATE DATABASE growth_loop_test;"
Get-Content .\db\schema.sql | docker exec -i $cid psql -U gle -d growth_loop_test
```

テストを実行：

```powershell
python -m pytest -v
```

期待される結果：

```
3 passed in X.XXs
```

## 🧠 設計方針（要点）

- **イベントログ中心設計**（append-only）
- **集計は後段で計算**（AI / 分析基盤へ拡張可能）
- `docs/00-master-design.md` を唯一の正とする
- MVP では「記録の完全性」を最優先

## 🧹 クリーンアップ（環境の削除）

検証が終わったあと、ローカル環境をきれいに戻す手順です。

### Docker コンテナ・ボリュームの削除

```powershell
# プロジェクトルートにいることを確認（growth-loop-engine フォルダ内）
docker compose down -v
```

> `-v` を付けることで、データベースのデータ（ボリューム）も一緒に削除されます。

### Docker イメージの削除（任意）

ディスク容量を節約したい場合：

```powershell
docker rmi postgres:16
```

### プロジェクトフォルダの削除

```powershell
cd ..
Remove-Item -Recurse -Force growth-loop-engine
```

これで clone 前の状態に戻ります。

## 開発

TODO

## ライセンス

TODO
