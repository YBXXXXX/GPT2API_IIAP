#!/usr/bin/env python3
"""SQLite control-plane storage (migrated from Rust src/storage/control.rs)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.models import AccountRecord, AccountSourceKind, ApiKeyRecord, UsageEventRecord
from storage.migrations import bootstrap_control_schema


class ControlDb:
    """SQLite wrapper for control-plane reads and writes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        # Ensure schema exists on first open
        conn = sqlite3.connect(str(path))
        try:
            bootstrap_control_schema(conn)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path))

    @staticmethod
    def _api_key_from_row(row: sqlite3.Row) -> ApiKeyRecord:
        return ApiKeyRecord(
            id=row["id"],
            name=row["name"],
            secret_hash=row["secret_hash"],
            secret_plaintext=row["secret_plaintext"],
            status=row["status"],
            quota_total_calls=row["quota_total_calls"],
            quota_used_calls=row["quota_used_calls"],
            route_strategy=row["route_strategy"],
            account_group_id=row["account_group_id"],
            request_max_concurrency=row["request_max_concurrency"],
            request_min_start_interval_ms=row["request_min_start_interval_ms"],
        )

    @staticmethod
    def _account_from_row(row: sqlite3.Row) -> AccountRecord:
        source_kind = AccountSourceKind(row["source_kind"])
        return AccountRecord(
            name=row["name"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            source_kind=source_kind,
            email=row["email"],
            user_id=row["user_id"],
            plan_type=row["plan_type"],
            default_model_slug=row["default_model_slug"],
            status=row["status"],
            quota_remaining=row["quota_remaining"],
            quota_known=bool(row["quota_known"]),
            restore_at=row["restore_at"],
            last_refresh_at=row["last_refresh_at"],
            last_used_at=row["last_used_at"],
            last_error=row["last_error"],
            success_count=row["success_count"],
            fail_count=row["fail_count"],
            request_max_concurrency=row["request_max_concurrency"],
            request_min_start_interval_ms=row["request_min_start_interval_ms"],
            browser_profile_json=row["browser_profile_json"] or "{}",
        )

    def list_accounts(self) -> list[AccountRecord]:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT name, access_token, refresh_token, source_kind, email, user_id, plan_type,
                   default_model_slug, status, quota_remaining, quota_known, restore_at,
                   last_refresh_at, last_used_at, last_error, success_count, fail_count,
                   request_max_concurrency, request_min_start_interval_ms, browser_profile_json
            FROM accounts
            ORDER BY name ASC
            """
        )
        rows = cur.fetchall()
        conn.close()
        return [self._account_from_row(r) for r in rows]

    def get_account(self, account_name: str) -> AccountRecord | None:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT name, access_token, refresh_token, source_kind, email, user_id, plan_type,
                   default_model_slug, status, quota_remaining, quota_known, restore_at,
                   last_refresh_at, last_used_at, last_error, success_count, fail_count,
                   request_max_concurrency, request_min_start_interval_ms, browser_profile_json
            FROM accounts
            WHERE name = ?
            LIMIT 1
            """,
            (account_name,),
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        return self._account_from_row(row)

    def find_account_by_access_token(self, access_token: str) -> AccountRecord | None:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT name, access_token, refresh_token, source_kind, email, user_id, plan_type,
                   default_model_slug, status, quota_remaining, quota_known, restore_at,
                   last_refresh_at, last_used_at, last_error, success_count, fail_count,
                   request_max_concurrency, request_min_start_interval_ms, browser_profile_json
            FROM accounts
            WHERE access_token = ?
            LIMIT 1
            """,
            (access_token,),
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        return self._account_from_row(row)

    def upsert_account(self, account: AccountRecord) -> None:
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO accounts (
                name, access_token, refresh_token, source_kind, email, user_id, plan_type,
                default_model_slug, status, quota_remaining, quota_known, restore_at,
                last_refresh_at, last_used_at, last_error, success_count, fail_count,
                request_max_concurrency, request_min_start_interval_ms, browser_profile_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                source_kind = excluded.source_kind,
                email = excluded.email,
                user_id = excluded.user_id,
                plan_type = excluded.plan_type,
                default_model_slug = excluded.default_model_slug,
                status = excluded.status,
                quota_remaining = excluded.quota_remaining,
                quota_known = excluded.quota_known,
                restore_at = excluded.restore_at,
                last_refresh_at = excluded.last_refresh_at,
                last_used_at = excluded.last_used_at,
                last_error = excluded.last_error,
                success_count = excluded.success_count,
                fail_count = excluded.fail_count,
                request_max_concurrency = excluded.request_max_concurrency,
                request_min_start_interval_ms = excluded.request_min_start_interval_ms,
                browser_profile_json = excluded.browser_profile_json
            """,
            (
                account.name,
                account.access_token,
                account.refresh_token,
                account.source_kind.value,
                account.email,
                account.user_id,
                account.plan_type,
                account.default_model_slug,
                account.status,
                account.quota_remaining,
                int(account.quota_known),
                account.restore_at,
                account.last_refresh_at,
                account.last_used_at,
                account.last_error,
                account.success_count,
                account.fail_count,
                account.request_max_concurrency,
                account.request_min_start_interval_ms,
                account.browser_profile_json,
            ),
        )
        conn.commit()
        conn.close()

    def delete_accounts_by_access_tokens(self, access_tokens: list[str]) -> int:
        if not access_tokens:
            return 0
        conn = self._connect()
        removed = 0
        for token in access_tokens:
            cur = conn.execute("DELETE FROM accounts WHERE access_token = ?", (token,))
            removed += cur.rowcount
        conn.commit()
        conn.close()
        return removed

    def upsert_api_key(self, key: ApiKeyRecord) -> None:
        conn = self._connect()
        conn.execute(
            """
            INSERT OR REPLACE INTO api_keys (
                id, name, secret_hash, secret_plaintext, status, quota_total_calls,
                quota_used_calls, route_strategy, account_group_id,
                request_max_concurrency, request_min_start_interval_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key.id,
                key.name,
                key.secret_hash,
                key.secret_plaintext,
                key.status,
                key.quota_total_calls,
                key.quota_used_calls,
                key.route_strategy,
                key.account_group_id,
                key.request_max_concurrency,
                key.request_min_start_interval_ms,
            ),
        )
        conn.commit()
        conn.close()

    def get_api_key(self, key_id: str) -> ApiKeyRecord | None:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, name, secret_hash, secret_plaintext, status, quota_total_calls,
                   quota_used_calls, route_strategy, account_group_id,
                   request_max_concurrency, request_min_start_interval_ms
            FROM api_keys
            WHERE id = ?
            LIMIT 1
            """,
            (key_id,),
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        return self._api_key_from_row(row)

    def find_api_key_by_secret_hash(self, secret_hash: str) -> ApiKeyRecord | None:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, name, secret_hash, secret_plaintext, status, quota_total_calls,
                   quota_used_calls, route_strategy, account_group_id,
                   request_max_concurrency, request_min_start_interval_ms
            FROM api_keys
            WHERE secret_hash = ?
            LIMIT 1
            """,
            (secret_hash,),
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        return self._api_key_from_row(row)

    def find_api_key_by_secret_plaintext(self, secret_plaintext: str) -> ApiKeyRecord | None:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, name, secret_hash, secret_plaintext, status, quota_total_calls,
                   quota_used_calls, route_strategy, account_group_id,
                   request_max_concurrency, request_min_start_interval_ms
            FROM api_keys
            WHERE secret_plaintext = ?
            LIMIT 1
            """,
            (secret_plaintext,),
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        return self._api_key_from_row(row)

    def list_api_keys(self) -> list[ApiKeyRecord]:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, name, secret_hash, secret_plaintext, status, quota_total_calls,
                   quota_used_calls, route_strategy, account_group_id,
                   request_max_concurrency, request_min_start_interval_ms
            FROM api_keys
            ORDER BY id ASC
            """
        )
        rows = cur.fetchall()
        conn.close()
        return [self._api_key_from_row(r) for r in rows]

    def delete_api_key(self, key_id: str) -> bool:
        conn = self._connect()
        cur = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        removed = cur.rowcount > 0
        conn.commit()
        conn.close()
        return removed

    def apply_success_settlement(self, event: UsageEventRecord) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE api_keys SET quota_used_calls = quota_used_calls + ? WHERE id = ?",
                (event.billable_images, event.key_id),
            )
            conn.execute(
                """
                INSERT INTO event_outbox (id, event_kind, payload_json, created_at, flushed_at)
                VALUES (?, 'usage_event', ?, ?, NULL)
                """,
                (event.event_id, event.model_dump_json(), event.created_at),
            )
            conn.execute(
                """
                INSERT INTO usage_events (
                    event_id, request_id, key_id, key_name, account_name, endpoint,
                    requested_model, resolved_upstream_model, requested_n, generated_n,
                    billable_images, status_code, latency_ms, error_code, error_message,
                    detail_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.request_id,
                    event.key_id,
                    event.key_name,
                    event.account_name,
                    event.endpoint,
                    event.requested_model,
                    event.resolved_upstream_model,
                    event.requested_n,
                    event.generated_n,
                    event.billable_images,
                    event.status_code,
                    event.latency_ms,
                    event.error_code,
                    event.error_message,
                    event.detail_ref,
                    event.created_at,
                ),
            )
        conn.close()

    def list_pending_outbox(self) -> list[str]:
        conn = self._connect()
        cur = conn.execute(
            "SELECT id FROM event_outbox WHERE flushed_at IS NULL ORDER BY created_at ASC"
        )
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows

    def list_pending_outbox_rows(self, limit: int) -> list[dict[str, Any]]:
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, payload_json FROM event_outbox
            WHERE flushed_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [{"id": r["id"], "payload": json.loads(r["payload_json"])} for r in cur.fetchall()]
        conn.close()
        return rows

    def mark_outbox_flushed(self, ids: list[str], flushed_at: int) -> None:
        if not ids:
            return
        conn = self._connect()
        with conn:
            for oid in ids:
                conn.execute(
                    "UPDATE event_outbox SET flushed_at = ? WHERE id = ?",
                    (flushed_at, oid),
                )
        conn.close()
