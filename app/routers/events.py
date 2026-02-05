import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.database import get_pool
from app.models import EventBatchIn, EventBatchOut, EventOut

router = APIRouter()


@router.post("/events", status_code=201, response_model=EventBatchOut)
async def create_events(body: EventBatchIn):
    pool = get_pool()

    async with pool.acquire() as conn:
        # user存在チェック
        user = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", body.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User {body.user_id} not found")

        # activity_id の存在チェック
        activity_ids = {e.activity_id for e in body.events if e.activity_id is not None}
        if activity_ids:
            rows = await conn.fetch(
                "SELECT id FROM activities WHERE id = ANY($1::uuid[])",
                list(activity_ids),
            )
            found = {row["id"] for row in rows}
            missing = activity_ids - found
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Activity not found: {missing.pop()}",
                )

        # トランザクション内で全件INSERT（アトミック）
        results = []
        async with conn.transaction():
            for event in body.events:
                occurred_at = event.occurred_at or datetime.now(timezone.utc)
                row = await conn.fetchrow(
                    """
                    INSERT INTO events (user_id, activity_id, event_type, payload, occurred_at)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, received_at
                    """,
                    body.user_id,
                    event.activity_id,
                    event.event_type,
                    json.dumps(event.payload),
                    occurred_at,
                )
                results.append(EventOut(id=row["id"], received_at=row["received_at"]))

    return EventBatchOut(accepted=len(results), events=results)
