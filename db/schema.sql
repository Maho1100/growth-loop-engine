-- Growth Loop Engine データベーススキーマ
-- 対象DB: PostgreSQL 15+

-- ===========================================
-- 拡張機能
-- ===========================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===========================================
-- users: ユーザーマスタ
-- ===========================================
CREATE TABLE IF NOT EXISTS users (
    user_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(255),
    traits      JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_external_id ON users (external_id);

-- ===========================================
-- sessions: セッション
-- ===========================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(user_id),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ
);

CREATE INDEX idx_sessions_user_id ON sessions (user_id);

-- ===========================================
-- events: イベントログ
-- ===========================================
CREATE TABLE IF NOT EXISTS events (
    event_id    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_name  VARCHAR(255) NOT NULL,
    user_id     UUID REFERENCES users(user_id),
    session_id  UUID REFERENCES sessions(session_id),
    properties  JSONB DEFAULT '{}',
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_user_id ON events (user_id);
CREATE INDEX idx_events_event_name ON events (event_name);
CREATE INDEX idx_events_occurred_at ON events (occurred_at);
