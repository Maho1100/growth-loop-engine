import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.database import get_pool
from app.models import (
    EventDetail,
    EventList,
    SessionStats,
    StreakInfo,
    UserSummary,
    WeeklyFrequency,
)

router = APIRouter()


async def _check_user(conn, user_id: UUID) -> None:
    user = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")


# §5.3 ストリーク計算SQL
STREAK_SQL = """
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
WHERE grp = (SELECT grp FROM numbered LIMIT 1)
"""

LONGEST_STREAK_SQL = """
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
),
streaks AS (
    SELECT COUNT(*) AS streak_len
    FROM numbered
    GROUP BY grp
)
SELECT COALESCE(MAX(streak_len), 0) AS longest_streak
FROM streaks
"""

LAST_ACTIVE_DATE_SQL = """
SELECT (MAX(occurred_at) AT TIME ZONE 'UTC')::date AS last_active
FROM events
WHERE user_id = $1
"""

# §5.3 セッション時間SQL
SESSION_SQL = """
WITH sessions AS (
    SELECT
        occurred_at AS started_at,
        LEAD(occurred_at) OVER (ORDER BY occurred_at) AS ended_at,
        event_type
    FROM events
    WHERE user_id = $1
      AND event_type IN ('engagement.session.started', 'engagement.session.ended')
      AND occurred_at >= now() - INTERVAL '30 days'
    ORDER BY occurred_at
)
SELECT
    COALESCE(AVG(EXTRACT(EPOCH FROM (ended_at - started_at)))::int, 0) AS avg_duration_sec,
    COUNT(*) AS total_sessions
FROM sessions
WHERE event_type = 'engagement.session.started'
  AND ended_at IS NOT NULL
  AND EXTRACT(EPOCH FROM (ended_at - started_at)) BETWEEN 10 AND 14400
"""

WEEKLY_FREQUENCY_SQL = """
WITH active_days AS (
    SELECT DISTINCT (occurred_at AT TIME ZONE 'UTC')::date AS d
    FROM events
    WHERE user_id = $1
      AND occurred_at >= now() - INTERVAL '28 days'
),
weekly AS (
    SELECT EXTRACT(ISOYEAR FROM d)::int AS yr,
           EXTRACT(WEEK FROM d)::int AS wk,
           COUNT(*) AS days_count
    FROM active_days
    GROUP BY yr, wk
)
SELECT
    COUNT(*)::int AS weeks_counted,
    COALESCE(AVG(days_count), 0)::float AS avg_days_per_week
FROM weekly
"""

THIS_WEEK_DAYS_SQL = """
SELECT COUNT(DISTINCT (occurred_at AT TIME ZONE 'UTC')::date)::int AS this_week_days
FROM events
WHERE user_id = $1
  AND (occurred_at AT TIME ZONE 'UTC')::date >= date_trunc('week', CURRENT_DATE)::date
"""


@router.get("/users/{user_id}/summary", response_model=UserSummary)
async def get_user_summary(user_id: UUID):
    pool = get_pool()

    async with pool.acquire() as conn:
        await _check_user(conn, user_id)

        # ストリーク
        streak_row = await conn.fetchrow(STREAK_SQL, user_id)
        longest_row = await conn.fetchrow(LONGEST_STREAK_SQL, user_id)
        last_active_row = await conn.fetchrow(LAST_ACTIVE_DATE_SQL, user_id)

        current_days = streak_row["current_streak"] if streak_row and streak_row["current_streak"] else 0
        longest_days = longest_row["longest_streak"] if longest_row else 0
        last_active_date = last_active_row["last_active"] if last_active_row else None

        # 週間頻度
        freq_row = await conn.fetchrow(WEEKLY_FREQUENCY_SQL, user_id)
        this_week_row = await conn.fetchrow(THIS_WEEK_DAYS_SQL, user_id)

        weeks_counted = freq_row["weeks_counted"] if freq_row else 0
        avg_days_per_week = round(freq_row["avg_days_per_week"], 1) if freq_row else 0.0
        this_week_days = this_week_row["this_week_days"] if this_week_row else 0

        # セッション
        session_row = await conn.fetchrow(SESSION_SQL, user_id)
        avg_duration_sec = session_row["avg_duration_sec"] if session_row else 0
        total_sessions = session_row["total_sessions"] if session_row else 0

    return UserSummary(
        user_id=user_id,
        computed_at=datetime.now(timezone.utc),
        streak=StreakInfo(
            current_days=current_days,
            longest_days=longest_days,
            last_active_date=last_active_date,
        ),
        weekly_frequency=WeeklyFrequency(
            weeks_counted=weeks_counted,
            avg_days_per_week=avg_days_per_week,
            this_week_days=this_week_days,
        ),
        session=SessionStats(
            avg_duration_sec=avg_duration_sec,
            total_sessions_30d=total_sessions,
        ),
    )


@router.get("/users/{user_id}/events", response_model=EventList)
async def get_user_events(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None, max_length=100),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
):
    pool = get_pool()

    async with pool.acquire() as conn:
        await _check_user(conn, user_id)

        # 動的にWHERE句を構築
        conditions = ["user_id = $1"]
        params: list = [user_id]
        idx = 2

        if event_type is not None:
            conditions.append(f"event_type = ${idx}")
            params.append(event_type)
            idx += 1
        if since is not None:
            conditions.append(f"occurred_at >= ${idx}")
            params.append(since)
            idx += 1
        if until is not None:
            conditions.append(f"occurred_at <= ${idx}")
            params.append(until)
            idx += 1

        where = " AND ".join(conditions)

        # COUNT
        count_sql = f"SELECT COUNT(*) FROM events WHERE {where}"
        total = await conn.fetchval(count_sql, *params)

        # SELECT
        select_sql = f"""
            SELECT id, event_type, payload, activity_id, occurred_at, received_at
            FROM events
            WHERE {where}
            ORDER BY occurred_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
        """
        params.extend([limit, offset])
        rows = await conn.fetch(select_sql, *params)

    events = [
        EventDetail(
            id=row["id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"],
            activity_id=row["activity_id"],
            occurred_at=row["occurred_at"],
            received_at=row["received_at"],
        )
        for row in rows
    ]

    return EventList(
        user_id=user_id,
        total=total,
        limit=limit,
        offset=offset,
        events=events,
    )
