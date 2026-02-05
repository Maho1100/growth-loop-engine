from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime, date

from app.validators import validate_event_type, validate_payload


# --- Request models (§5.2) ---

class EventIn(BaseModel):
    event_type: str = Field(
        ...,
        min_length=5,
        max_length=100,
        examples=["learning.answer.submitted"]
    )
    payload: dict = Field(default_factory=dict)
    activity_id: UUID | None = None
    occurred_at: datetime | None = None  # 省略時はサーバー時刻

    @field_validator('event_type')
    @classmethod
    def check_event_type(cls, v: str) -> str:
        error = validate_event_type(v)
        if error:
            raise ValueError(error)
        return v

    @field_validator('payload')
    @classmethod
    def check_payload_size(cls, v: dict) -> dict:
        error = validate_payload(v)
        if error:
            raise ValueError(error)
        return v


class EventBatchIn(BaseModel):
    user_id: UUID
    events: list[EventIn] = Field(
        ...,
        min_length=1,
        max_length=100
    )


class EventOut(BaseModel):
    id: UUID
    received_at: datetime


class EventBatchOut(BaseModel):
    accepted: int
    events: list[EventOut]


# --- Response models ---

class EventDetail(BaseModel):
    id: UUID
    event_type: str
    payload: dict
    activity_id: UUID | None
    occurred_at: datetime
    received_at: datetime


class EventList(BaseModel):
    user_id: UUID
    total: int
    limit: int
    offset: int
    events: list[EventDetail]


class StreakInfo(BaseModel):
    current_days: int
    longest_days: int
    last_active_date: date | None


class WeeklyFrequency(BaseModel):
    weeks_counted: int
    avg_days_per_week: float
    this_week_days: int


class SessionStats(BaseModel):
    avg_duration_sec: int
    total_sessions_30d: int


class UserSummary(BaseModel):
    user_id: UUID
    computed_at: datetime
    streak: StreakInfo
    weekly_frequency: WeeklyFrequency
    session: SessionStats
