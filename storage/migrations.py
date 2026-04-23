#!/usr/bin/env python3
"""Schema bootstrap helpers for SQLite (migrated from Rust src/storage/migrations.rs)."""

import sqlite3


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    name TEXT PRIMARY KEY NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    source_kind TEXT NOT NULL DEFAULT 'token',
    email TEXT,
    user_id TEXT,
    plan_type TEXT,
    default_model_slug TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    quota_remaining INTEGER NOT NULL DEFAULT 0,
    quota_known INTEGER NOT NULL DEFAULT 0,
    restore_at TEXT,
    last_refresh_at INTEGER,
    last_used_at INTEGER,
    last_error TEXT,
    success_count INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    request_max_concurrency INTEGER,
    request_min_start_interval_ms INTEGER,
    browser_profile_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS account_groups (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_group_members (
    group_id TEXT NOT NULL,
    account_name TEXT NOT NULL,
    PRIMARY KEY (group_id, account_name)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    secret_plaintext TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    quota_total_calls INTEGER NOT NULL DEFAULT 0,
    quota_used_calls INTEGER NOT NULL DEFAULT 0,
    route_strategy TEXT NOT NULL DEFAULT 'auto',
    account_group_id TEXT,
    request_max_concurrency INTEGER,
    request_min_start_interval_ms INTEGER
);

CREATE TABLE IF NOT EXISTS runtime_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    refresh_min_seconds INTEGER NOT NULL DEFAULT 300,
    refresh_max_seconds INTEGER NOT NULL DEFAULT 3600,
    refresh_jitter_seconds INTEGER NOT NULL DEFAULT 60,
    default_request_max_concurrency INTEGER NOT NULL DEFAULT 1,
    default_request_min_start_interval_ms INTEGER NOT NULL DEFAULT 0,
    event_flush_batch_size INTEGER NOT NULL DEFAULT 100,
    event_flush_interval_seconds INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS event_outbox (
    id TEXT PRIMARY KEY NOT NULL,
    event_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    flushed_at INTEGER
);

CREATE TABLE IF NOT EXISTS usage_events (
    event_id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL,
    key_id TEXT NOT NULL,
    key_name TEXT NOT NULL,
    account_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    requested_model TEXT NOT NULL,
    resolved_upstream_model TEXT NOT NULL,
    requested_n INTEGER NOT NULL DEFAULT 0,
    generated_n INTEGER NOT NULL DEFAULT 0,
    billable_images INTEGER NOT NULL DEFAULT 0,
    status_code INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    detail_ref TEXT,
    created_at INTEGER NOT NULL
);
"""


def bootstrap_control_schema(conn: sqlite3.Connection) -> None:
    """Creates all control-plane tables if they do not exist yet."""
    conn.executescript(CREATE_TABLES_SQL)
    conn.execute("PRAGMA journal_mode = WAL;")
