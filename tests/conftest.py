import os
from pathlib import Path

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# テスト用DB URL（環境変数 or デフォルト）
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://gle:gle@localhost:5432/growth_loop_test"
)

# schema.sql のパス
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


@pytest_asyncio.fixture
async def db_pool():
    pool = await asyncpg.create_pool(TEST_DATABASE_URL)
    # schema適用
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        # テーブルをクリーンアップしてから作成
        await conn.execute("DROP TABLE IF EXISTS events CASCADE")
        await conn.execute("DROP TABLE IF EXISTS activities CASCADE")
        await conn.execute("DROP TABLE IF EXISTS users CASCADE")
        await conn.execute(schema_sql)
    yield pool
    # テスト後クリーンアップ
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM events")
        await conn.execute("DELETE FROM activities")
        await conn.execute("DELETE FROM users")
    await pool.close()


@pytest_asyncio.fixture
async def client(db_pool):
    # app の database モジュールの pool を差し替える
    import app.database as db_mod
    db_mod.pool = db_pool

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
