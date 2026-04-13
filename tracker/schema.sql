-- Tarahumara Ultra Tracker — Database Schema
-- Run on every startup; all statements are idempotent (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS activities (
    id              SERIAL PRIMARY KEY,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    garmin_id       BIGINT UNIQUE,
    activity_date   DATE NOT NULL,
    week_number     SMALLINT NOT NULL,
    activity_type   TEXT,
    activity_name   TEXT,
    distance_km     REAL,
    elevation_m     REAL,
    duration_min    REAL,
    avg_hr          REAL,
    avg_pace        TEXT,
    calories        REAL,
    sets            INTEGER,
    reps            INTEGER,
    route_svg       TEXT,
    raw_json        JSONB,
    synced_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activities_week ON activities (week_number, profile_id);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities (activity_date);

CREATE TABLE IF NOT EXISTS daily_health (
    date            DATE NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    sleep_hours     REAL,
    sleep_score     SMALLINT,
    deep_sleep_min  REAL,
    rem_sleep_min   REAL,
    light_sleep_min REAL,
    hrv_weekly_avg  REAL,
    hrv_last_night  REAL,
    resting_hr      SMALLINT,
    body_battery_am SMALLINT,
    body_battery_pm SMALLINT,
    training_readiness SMALLINT,
    stress_avg      SMALLINT,
    spo2_avg        REAL,
    weight_kg       REAL,
    body_fat_pct    REAL,
    raw_json        JSONB,
    synced_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date, profile_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    question        TEXT NOT NULL,
    category        TEXT NOT NULL,
    response        TEXT NOT NULL,
    week_number     SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS week_snapshots (
    week_number     SMALLINT NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    data            JSONB NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (week_number, profile_id)
);

CREATE TABLE IF NOT EXISTS training_plan (
    week_number     SMALLINT NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    phase           TEXT NOT NULL,
    is_recovery     BOOLEAN DEFAULT FALSE,
    distance_km     REAL,
    vert_m          REAL,
    long_run_km     REAL,
    gym_sessions    SMALLINT,
    series_type     TEXT,
    workouts        JSONB,
    start_date      TEXT,
    end_date        TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (week_number, profile_id)
);

CREATE TABLE IF NOT EXISTS plan_changes (
    id              SERIAL PRIMARY KEY,
    week_number     SMALLINT NOT NULL,
    profile_id      TEXT NOT NULL DEFAULT 'default',
    field           TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    reason          TEXT,
    source          TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plan_changes_week ON plan_changes (week_number, profile_id);
