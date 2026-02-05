-- Migration: 001_create_tables.sql

BEGIN;

-- 1. users
CREATE TABLE users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id   VARCHAR(255) UNIQUE,
    display_name  VARCHAR(100),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. activities
CREATE TABLE activities (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id),
    slug        VARCHAR(100) NOT NULL,
    title       VARCHAR(255),
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, slug)
);

-- 3. events
CREATE TABLE events (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID         NOT NULL REFERENCES users(id),
    activity_id   UUID         REFERENCES activities(id),
    event_type    VARCHAR(100) NOT NULL,
    payload       JSONB        NOT NULL DEFAULT '{}',
    occurred_at   TIMESTAMPTZ  NOT NULL,
    received_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_user_occurred
    ON events (user_id, occurred_at DESC);

CREATE INDEX idx_events_user_type
    ON events (user_id, event_type, occurred_at DESC);

CREATE INDEX idx_events_activity
    ON events (activity_id, occurred_at DESC)
    WHERE activity_id IS NOT NULL;

COMMIT;
