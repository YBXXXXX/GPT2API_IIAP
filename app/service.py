#!/usr/bin/env python3
"""Service orchestration layer (migrated from Rust src/service.rs)."""

from __future__ import annotations

import hashlib
import asyncio
import time
import uuid
from typing import Any

from app.models import (
    AccountRecord,
    AccountRouteCandidate,
    AccountUpdate,
    ApiKeyCreate,
    ApiKeyRecord,
    ApiKeySecretRecord,
    ApiKeyUpdate,
    ChatgptImageResult,
    ImageEditInput,
    RouteStrategy,
    UsageEventRecord,
)
from scheduler.local_scheduler import Lease, LocalRequestScheduler
from scheduler.routing import select_best_candidate
from storage.control import ControlDb
from upstream.chatgpt import ChatgptUpstreamClient


class PublicAuthError(Exception):
    """Public-key authentication failure classes exposed to downstream callers."""

    pass


class InvalidKey(PublicAuthError):
    pass


class Disabled(PublicAuthError):
    pass


class QuotaExhausted(PublicAuthError):
    pass


class AppService:
    """Shared runtime service backing public and admin HTTP handlers."""

    def __init__(
        self,
        storage: ControlDb,
        admin_token: str,
        upstream: ChatgptUpstreamClient,
    ) -> None:
        self.storage = storage
        self.admin_token = admin_token.strip()
        self.upstream = upstream
        self.key_scheduler = LocalRequestScheduler()
        self.account_scheduler = LocalRequestScheduler()
        self._account_retry_after: dict[str, float] = {}
        self._account_failure_streaks: dict[str, int] = {}
        self._ensure_default_api_key()

    def _ensure_default_api_key(self) -> None:
        key = ApiKeyRecord(
            id="default",
            name="default",
            secret_hash=sha256_hex(self.admin_token),
            secret_plaintext=self.admin_token,
            status="active",
            quota_total_calls=2_147_483_647 // 4,
            quota_used_calls=0,
            route_strategy="auto",
        )
        self.storage.upsert_api_key(key)

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #

    def is_admin_token(self, bearer: str) -> bool:
        return bool(bearer.strip()) and bearer.strip() == self.admin_token

    def authenticate_public_key(self, bearer: str) -> ApiKeyRecord:
        bearer = bearer.strip()
        if not bearer:
            raise InvalidKey("invalid_key")
        expected_hash = sha256_hex(bearer)
        key = self.storage.find_api_key_by_secret_plaintext(bearer)
        if key is None:
            key = self.storage.find_api_key_by_secret_hash(expected_hash)
        if key is None:
            raise InvalidKey("invalid_key")
        # backfill plaintext if needed
        if key.secret_plaintext != bearer or key.secret_hash != expected_hash:
            key.secret_plaintext = bearer
            key.secret_hash = expected_hash
            self.storage.upsert_api_key(key)
        if key.status != "active":
            raise Disabled("disabled")
        ensure_key_can_consume(key, 1)
        return key

    # ------------------------------------------------------------------ #
    # Account management
    # ------------------------------------------------------------------ #

    def import_accounts(self, items: list[tuple[str, str]]) -> list[AccountRecord]:
        """items: list of (kind, raw) where kind is 'token' or 'session_json'."""
        from accounts.importer import build_account_record, parse_access_token_seed, parse_session_seed

        for kind, raw in items:
            if kind == "token":
                seed = parse_access_token_seed(raw)
            elif kind == "session_json":
                seed = parse_session_seed(raw)
            else:
                continue
            self.storage.upsert_account(build_account_record(seed))
        return self.storage.list_accounts()

    def import_sub2api_accounts(self, data: dict[str, Any]) -> list[AccountRecord]:
        """Import accounts from sub2api JSON export.

        Expected format:
        {
            "accounts": [
                {
                    "name": "...",
                    "credentials": {
                        "access_token": "...",
                        "refresh_token": "...",
                        "email": "...",
                        "plan_type": "plus"
                    },
                    "extra": { ... }
                }
            ]
        }
        """
        import json

        accounts = data.get("accounts", [])
        imported: list[AccountRecord] = []
        for item in accounts:
            creds = item.get("credentials", {})
            access_token = creds.get("access_token", "")
            if not access_token:
                continue
            refresh_token = creds.get("refresh_token")
            email = creds.get("email") or item.get("extra", {}).get("email")
            plan_type = creds.get("plan_type") or item.get("extra", {}).get("plan_type")
            name = item.get("name", "")
            if not name:
                # Derive from access token hash
                name = f"acct_{hashlib.sha1(access_token.encode()).hexdigest()[:12]}"
            account = AccountRecord(
                name=name,
                access_token=access_token,
                refresh_token=refresh_token,
                source_kind="token",
                email=email,
                plan_type=plan_type,
                status="active",
                request_max_concurrency=1,
                browser_profile_json="{}",
            )
            self.storage.upsert_account(account)
            imported.append(account)
        return imported

    def delete_accounts(self, access_tokens: list[str]) -> list[AccountRecord]:
        self.storage.delete_accounts_by_access_tokens(access_tokens)
        return self.storage.list_accounts()

    async def refresh_accounts(self, access_tokens: list[str] | None = None) -> list[AccountRecord]:
        targets = self.storage.list_accounts()
        if access_tokens:
            wanted = {t.strip() for t in access_tokens}
            targets = [a for a in targets if a.access_token.strip() in wanted]
        for account in targets:
            refreshed = await self._refresh_account(account)
            self.storage.upsert_account(refreshed)
        return self.storage.list_accounts()

    def update_account(self, access_token: str, update: AccountUpdate) -> AccountRecord | None:
        account = self.storage.find_account_by_access_token(access_token.strip())
        if account is None:
            return None
        if update.plan_type is not None:
            account.plan_type = update.plan_type
        if update.status is not None:
            account.status = update.status
        if update.quota_remaining is not None:
            account.quota_remaining = update.quota_remaining
            account.quota_known = True
        if update.restore_at is not None:
            account.restore_at = update.restore_at
        if update.browser_profile is not None:
            account.browser_profile_json = update.browser_profile.model_dump_json()
        if update.request_max_concurrency is not None:
            account.request_max_concurrency = update.request_max_concurrency
        if update.request_min_start_interval_ms is not None:
            account.request_min_start_interval_ms = update.request_min_start_interval_ms
        self.storage.upsert_account(account)
        return account

    # ------------------------------------------------------------------ #
    # API key management
    # ------------------------------------------------------------------ #

    def create_api_key(self, input: ApiKeyCreate) -> ApiKeySecretRecord:
        secret_plaintext = generate_api_key_plaintext()
        key = ApiKeyRecord(
            id=f"key_{uuid.uuid4().hex}",
            name=normalize_required_string(input.name, "name"),
            secret_hash=sha256_hex(secret_plaintext),
            secret_plaintext=secret_plaintext,
            status=normalize_api_key_status(input.status or "active"),
            quota_total_calls=validate_quota_total_calls(input.quota_total_calls),
            quota_used_calls=0,
            route_strategy=normalize_route_strategy(input.route_strategy or "auto"),
            account_group_id=input.account_group_id,
            request_max_concurrency=input.request_max_concurrency,
            request_min_start_interval_ms=input.request_min_start_interval_ms,
        )
        self.storage.upsert_api_key(key)
        return ApiKeySecretRecord(key=key, secret_plaintext=secret_plaintext)

    def update_api_key(self, key_id: str, update: ApiKeyUpdate) -> ApiKeyRecord | None:
        key = self.storage.get_api_key(key_id)
        if key is None:
            return None
        if update.name is not None:
            key.name = normalize_required_string(update.name, "name")
        if update.status is not None:
            key.status = normalize_api_key_status(update.status)
        if update.quota_total_calls is not None:
            key.quota_total_calls = validate_quota_total_calls(update.quota_total_calls)
        if update.route_strategy is not None:
            key.route_strategy = normalize_route_strategy(update.route_strategy)
        if update.account_group_id is not None:
            key.account_group_id = update.account_group_id
        if update.request_max_concurrency is not None:
            key.request_max_concurrency = update.request_max_concurrency
        if update.request_min_start_interval_ms is not None:
            key.request_min_start_interval_ms = update.request_min_start_interval_ms
        self.storage.upsert_api_key(key)
        return key

    def rotate_api_key(self, key_id: str) -> ApiKeySecretRecord | None:
        key = self.storage.get_api_key(key_id)
        if key is None:
            return None
        secret_plaintext = generate_api_key_plaintext()
        key.secret_hash = sha256_hex(secret_plaintext)
        key.secret_plaintext = secret_plaintext
        self.storage.upsert_api_key(key)
        return ApiKeySecretRecord(key=key, secret_plaintext=secret_plaintext)

    def delete_api_key(self, key_id: str) -> bool:
        return self.storage.delete_api_key(key_id)

    # ------------------------------------------------------------------ #
    # Public image execution
    # ------------------------------------------------------------------ #

    async def generate_images_for_key(
        self, key: ApiKeyRecord, prompt: str, requested_model: str, requested_n: int
    ) -> ChatgptImageResult:
        return await self._execute_public_image_request(
            key, prompt, requested_model, requested_n, None, "/v1/images/generations"
        )

    async def edit_images_for_key(
        self,
        key: ApiKeyRecord,
        prompt: str,
        requested_model: str,
        requested_n: int,
        edit_input: ImageEditInput,
    ) -> ChatgptImageResult:
        return await self._execute_public_image_request(
            key, prompt, requested_model, requested_n, edit_input, "/v1/images/edits"
        )

    async def generate_images_for_account(
        self,
        account_name: str,
        prompt: str,
        requested_model: str,
        requested_n: int,
    ) -> ChatgptImageResult:
        """Generate images using a specific account directly (no API key required)."""
        account = self.storage.get_account(account_name)
        if account is None:
            raise RuntimeError(f"account not found: {account_name}")

        requested_n = max(1, min(requested_n, 4))
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        images = []
        resolved_model = ""
        last_error: str | None = None

        for _ in range(requested_n):
            account = await self._refresh_account_if_needed(account)
            if not is_account_routeable(account):
                last_error = "account not routeable"
                continue
            try:
                result = await self.upstream.generate_image(
                    account, prompt, requested_model
                )
                resolved_model = result.resolved_model or resolved_model
                images.extend(result.data)
                self._record_account_success(account)
            except Exception as e:
                self._record_account_failure(account, str(e))
                last_error = str(e)
                if is_token_invalid_error(str(e)):
                    continue

        if not images:
            raise RuntimeError(last_error or "image generation failed")

        return ChatgptImageResult(
            created=int(time.time()),
            data=images,
            resolved_model=resolved_model or requested_model,
        )

    async def _execute_public_image_request(
        self,
        key: ApiKeyRecord,
        prompt: str,
        requested_model: str,
        requested_n: int,
        edit_input: ImageEditInput | None,
        endpoint: str,
    ) -> ChatgptImageResult:
        ensure_key_can_consume(key, requested_n)
        key_lease = await self._acquire_key_lease(key)
        try:
            requested_n = max(1, min(requested_n, 4))
            request_id = str(uuid.uuid4())
            started = time.monotonic()
            images = []
            resolved_model = ""
            selected_account_name = ""
            last_error: str | None = None

            for _ in range(requested_n):
                account, account_lease = await self._acquire_account_for_key(key)
                try:
                    account = await self._refresh_account_if_needed(account)
                    if not is_account_routeable(account):
                        last_error = "no available accounts"
                        continue
                    selected_account_name = account.name
                    try:
                        if edit_input is not None:
                            result = await self.upstream.edit_image(
                                account,
                                prompt,
                                requested_model,
                                edit_input.image_data,
                                edit_input.file_name,
                                edit_input.mime_type,
                            )
                        else:
                            result = await self.upstream.generate_image(
                                account, prompt, requested_model
                            )
                        resolved_model = result.resolved_model or resolved_model
                        images.extend(result.data)
                        self._record_account_success(account)
                    except Exception as e:
                        self._record_account_failure(account, str(e))
                        last_error = str(e)
                        if is_token_invalid_error(str(e)):
                            continue
                finally:
                    account_lease.release()

            if not images:
                raise RuntimeError(last_error or "image generation failed")

            result = ChatgptImageResult(
                created=int(time.time()),
                data=images,
                resolved_model=resolved_model or requested_model,
            )
            event = UsageEventRecord(
                event_id=str(uuid.uuid4()),
                request_id=request_id,
                key_id=key.id,
                key_name=key.name,
                account_name=selected_account_name,
                endpoint=endpoint,
                requested_model=requested_model,
                resolved_upstream_model=result.resolved_model,
                requested_n=requested_n,
                generated_n=len(images),
                billable_images=len(images),
                status_code=200,
                latency_ms=int((time.monotonic() - started) * 1000),
                created_at=int(time.time()),
            )
            self.storage.apply_success_settlement(event)
            return result
        finally:
            key_lease.release()

    # ------------------------------------------------------------------ #
    # Scheduler helpers
    # ------------------------------------------------------------------ #

    async def _acquire_key_lease(self, key: ApiKeyRecord) -> Lease:
        while True:
            lease = self.key_scheduler.try_acquire(
                f"api-key:{key.id}",
                key.request_max_concurrency,
                key.request_min_start_interval_ms,
            )
            if isinstance(lease, Lease):
                return lease
            await self.key_scheduler.wait_for_available(lease.wait_ms)

    def select_best_account(self) -> AccountRecord | None:
        """Pick the account with highest quota (no lease acquired yet)."""
        accounts = self.storage.list_accounts()
        candidates = [
            AccountRouteCandidate(
                name=a.name,
                quota_remaining=a.quota_remaining,
                quota_known=a.quota_known,
                last_routed_at_ms=a.last_used_at or 0,
            )
            for a in accounts
            if is_account_selectable(a) and not self._is_account_in_backoff(a.name)
        ]
        selected = select_best_candidate(RouteStrategy.AUTO, candidates)
        if selected is None:
            return None
        for a in accounts:
            if a.name == selected.name:
                return a
        return None

    async def _acquire_account_for_key(
        self, key: ApiKeyRecord
    ) -> tuple[AccountRecord, Lease]:
        while True:
            accounts = self.storage.list_accounts()
            remaining = {
                a.name: a
                for a in accounts
                if is_account_selectable(a) and not self._is_account_in_backoff(a.name)
            }
            backoff_wait_ms = self._next_account_backoff_wait_ms(accounts)
            if not remaining and backoff_wait_ms <= 0:
                raise RuntimeError("no available accounts")

            waits: list[int] = []
            while remaining:
                candidates = [
                    AccountRouteCandidate(
                        name=a.name,
                        quota_remaining=a.quota_remaining,
                        quota_known=a.quota_known,
                        last_routed_at_ms=a.last_used_at or 0,
                    )
                    for a in remaining.values()
                ]
                strategy = (
                    RouteStrategy.FIXED
                    if key.route_strategy.strip().lower() == "fixed"
                    else RouteStrategy.AUTO
                )
                selected = select_best_candidate(strategy, candidates)
                if selected is None:
                    raise RuntimeError("no available accounts")
                account = remaining.pop(selected.name)
                lease = self.account_scheduler.try_acquire(
                    f"account:{account.name}",
                    effective_account_max_concurrency(account),
                    account.request_min_start_interval_ms,
                )
                if isinstance(lease, Lease):
                    return account, lease
                waits.append(lease.wait_ms)

            wait = min(waits) if waits else backoff_wait_ms
            await self._wait_for_account_availability(wait)

    async def acquire_best_account_for_queue(self) -> tuple[AccountRecord, Lease]:
        """Pick the best currently available account for anonymous queued jobs."""
        while True:
            accounts = self.storage.list_accounts()
            available = [
                a
                for a in accounts
                if is_account_selectable(a) and not self._is_account_in_backoff(a.name)
            ]
            backoff_wait_ms = self._next_account_backoff_wait_ms(accounts)
            if not available and backoff_wait_ms <= 0:
                raise RuntimeError("no available accounts")

            candidates = [
                AccountRouteCandidate(
                    name=a.name,
                    quota_remaining=a.quota_remaining,
                    quota_known=a.quota_known,
                    last_routed_at_ms=a.last_used_at or 0,
                )
                for a in available
            ]
            selected = select_best_candidate(RouteStrategy.AUTO, candidates)
            if selected is None:
                await self._wait_for_account_availability(backoff_wait_ms)
                continue

            account = next(a for a in available if a.name == selected.name)
            lease = self.account_scheduler.try_acquire(
                f"account:{account.name}",
                effective_account_max_concurrency(account),
                account.request_min_start_interval_ms,
            )
            if isinstance(lease, Lease):
                return account, lease

            wait = lease.wait_ms
            if backoff_wait_ms > 0:
                wait = min(wait, backoff_wait_ms) if wait > 0 else backoff_wait_ms
            await self._wait_for_account_availability(wait)

    async def _acquire_account_lease(self, account: AccountRecord) -> Lease:
        """Acquire lease for a specific account, waiting if needed."""
        while True:
            lease = self.account_scheduler.try_acquire(
                f"account:{account.name}",
                effective_account_max_concurrency(account),
                account.request_min_start_interval_ms,
            )
            if isinstance(lease, Lease):
                return lease
            await self._wait_for_account_availability(lease.wait_ms)

    async def _wait_for_account_availability(self, wait_ms: int) -> None:
        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000.0)
            return
        await self.account_scheduler.wait_for_available(wait_ms)

    # ------------------------------------------------------------------ #
    # Account refresh
    # ------------------------------------------------------------------ #

    async def _refresh_account_if_needed(self, account: AccountRecord) -> AccountRecord:
        if account.last_refresh_at is None:
            return account
        stale = int(time.time()) - account.last_refresh_at >= 300
        if not stale:
            return account
        refreshed = await self._refresh_account(account)
        self.storage.upsert_account(refreshed)
        return refreshed

    async def _refresh_account(self, account: AccountRecord) -> AccountRecord:
        try:
            metadata = await self.upstream.fetch_account_metadata(account)
            account.email = metadata.get("email") or account.email
            account.user_id = metadata.get("user_id") or account.user_id
            account.plan_type = metadata.get("plan_type") or account.plan_type
            account.default_model_slug = metadata.get("default_model_slug") or account.default_model_slug
            qr = metadata.get("quota_remaining")
            if qr is not None:
                account.quota_remaining = qr
                account.quota_known = True
            else:
                account.quota_known = False
            account.last_refresh_at = int(time.time())
            account.last_error = None
        except Exception as e:
            account.last_refresh_at = int(time.time())
            account.last_error = str(e)
            if is_token_invalid_error(str(e)):
                account.status = "invalid"
                account.quota_remaining = 0
                account.quota_known = True
        return account

    # ------------------------------------------------------------------ #
    # Success / failure tracking
    # ------------------------------------------------------------------ #

    def _record_account_success(self, account: AccountRecord) -> None:
        account.success_count += 1
        account.last_used_at = int(time.time())
        account.last_error = None
        self._account_failure_streaks.pop(account.name, None)
        self._account_retry_after.pop(account.name, None)
        if account.quota_known:
            account.quota_remaining = max(0, account.quota_remaining - 1)
            account.status = "limited" if account.quota_remaining == 0 else "active"
        else:
            account.status = "active"
        self.storage.upsert_account(account)

    def _record_account_failure(self, account: AccountRecord, error_message: str) -> None:
        account.fail_count += 1
        account.last_used_at = int(time.time())
        account.last_error = error_message
        if is_token_invalid_error(error_message):
            account.status = "invalid"
            account.quota_remaining = 0
            account.quota_known = True
            self._account_failure_streaks.pop(account.name, None)
            self._account_retry_after.pop(account.name, None)
        elif should_backoff_account_error(error_message):
            streak = self._account_failure_streaks.get(account.name, 0) + 1
            self._account_failure_streaks[account.name] = streak
            self._account_retry_after[account.name] = time.monotonic() + account_backoff_seconds(streak, error_message)
        self.storage.upsert_account(account)

    def _is_account_in_backoff(self, account_name: str) -> bool:
        retry_after = self._account_retry_after.get(account_name)
        if retry_after is None:
            return False
        if time.monotonic() >= retry_after:
            self._account_retry_after.pop(account_name, None)
            return False
        return True

    def _next_account_backoff_wait_ms(self, accounts: list[AccountRecord]) -> int:
        waits = [
            max(0, int((retry_after - time.monotonic()) * 1000))
            for account_name, retry_after in self._account_retry_after.items()
            if any(a.name == account_name and is_account_selectable(a) for a in accounts)
        ]
        return min(waits) if waits else 0


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key_plaintext() -> str:
    return f"sk-{uuid.uuid4().hex}"


def normalize_api_key_status(raw: str) -> str:
    value = raw.strip().lower()
    if value == "active":
        return "active"
    if value == "disabled":
        return "disabled"
    raise ValueError("status must be active or disabled")


def normalize_route_strategy(raw: str) -> str:
    value = raw.strip().lower()
    if value in ("", "auto"):
        return "auto"
    if value == "fixed":
        return "fixed"
    raise ValueError("route_strategy must be auto or fixed")


def normalize_required_string(raw: str, field_name: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


def validate_quota_total_calls(value: int) -> int:
    if value < 0:
        raise ValueError("quota_total_calls must be >= 0")
    return value


def ensure_key_can_consume(key: ApiKeyRecord, cost: int) -> None:
    if key.status != "active":
        raise Disabled("disabled")
    if cost <= 0:
        return
    if key.quota_total_calls <= 0 or key.quota_used_calls + cost > key.quota_total_calls:
        raise QuotaExhausted("quota_exhausted")


def is_account_selectable(account: AccountRecord) -> bool:
    return account.status not in ("invalid", "disabled")


def is_account_routeable(account: AccountRecord) -> bool:
    return account.status == "active"


def effective_account_max_concurrency(account: AccountRecord) -> int:
    return 1


def is_token_invalid_error(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "token_invalidated",
            "token_revoked",
            "authentication token has been invalidated",
            "invalidated oauth token",
            "/backend-api/me failed: http 401",
        )
    )


def should_backoff_account_error(message: str) -> bool:
    text = message.lower()
    if is_token_invalid_error(text):
        return False
    if "no file ids found after polling" in text:
        return False
    if is_prompt_rejection_error(text):
        return False
    return any(
        phrase in text
        for phrase in (
            "timed out",
            "timeout",
            "http/2 stream",
            "internal_error",
            "failed to perform",
            "connection",
            "connect",
            "proxy",
            "502",
            "503",
            "504",
            "429",
            "rate limit",
            "quota_exhausted",
        )
    )


def is_prompt_rejection_error(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "该提示可能违反",
            "防护限制",
            "修改提示语",
            "违反了",
            "违反我们的政策",
            "非常抱歉",
            "sorry, this prompt",
            "may violate",
            "safety policy",
            "policy",
            "cannot help with that request",
            "can't help with that request",
            "unable to generate",
        )
    )


def account_backoff_seconds(streak: int, message: str) -> int:
    text = message.lower()
    if "429" in text or "rate limit" in text:
        base = 60
    elif "timed out" in text or "timeout" in text:
        base = 45
    else:
        base = 30
    return min(300, base * max(1, min(streak, 4)))
