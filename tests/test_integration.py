"""
結合テスト: ユーザー作成 → POST /v1/events → GET /v1/users/{id}/summary
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone, timedelta


@pytest.mark.asyncio
async def test_post_events_then_get_summary(client, db_pool):
    # 1) テスト用ユーザーを直接DBに作成
    user_id = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, external_id, display_name) VALUES ($1, $2, $3)",
            user_id, "test-ext-001", "Test User",
        )

    # 2) POST /v1/events — セッション開始 + 回答 + セッション終了
    now = datetime.now(timezone.utc)
    session_start = now - timedelta(hours=1)
    answer_time = now - timedelta(minutes=30)
    session_end = now - timedelta(minutes=5)

    resp = await client.post("/v1/events", json={
        "user_id": str(user_id),
        "events": [
            {
                "event_type": "engagement.session.started",
                "payload": {"client": "web", "version": "1.0.0"},
                "occurred_at": session_start.isoformat(),
            },
            {
                "event_type": "learning.answer.submitted",
                "payload": {"question_id": "q-01", "selected": "A", "correct": True, "time_ms": 3000},
                "occurred_at": answer_time.isoformat(),
            },
            {
                "event_type": "engagement.session.ended",
                "payload": {"reason": "user_exit"},
                "occurred_at": session_end.isoformat(),
            },
        ],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["accepted"] == 3
    assert len(data["events"]) == 3

    # 3) GET /v1/users/{id}/summary
    resp = await client.get(f"/v1/users/{user_id}/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["user_id"] == str(user_id)
    assert summary["streak"]["current_days"] >= 1
    assert summary["session"]["total_sessions_30d"] >= 1
    assert summary["session"]["avg_duration_sec"] > 0

    # 4) GET /v1/users/{id}/events
    resp = await client.get(f"/v1/users/{user_id}/events")
    assert resp.status_code == 200
    event_list = resp.json()
    assert event_list["total"] == 3
    assert len(event_list["events"]) == 3


@pytest.mark.asyncio
async def test_post_events_unknown_user_returns_404(client):
    fake_id = uuid4()
    resp = await client.post("/v1/events", json={
        "user_id": str(fake_id),
        "events": [
            {
                "event_type": "engagement.session.started",
                "payload": {},
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            },
        ],
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_events_invalid_event_type_returns_422(client, db_pool):
    user_id = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, external_id, display_name) VALUES ($1, $2, $3)",
            user_id, "test-ext-002", "Test User 2",
        )

    resp = await client.post("/v1/events", json={
        "user_id": str(user_id),
        "events": [
            {
                "event_type": "INVALID",
                "payload": {},
            },
        ],
    })
    assert resp.status_code == 422
