#!/usr/bin/env python3
"""Shared domain models (migrated from Rust src/models.rs)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AccountSourceKind(str, Enum):
    """Supported sources for imported ChatGPT access credentials."""

    TOKEN = "token"
    SESSION_JSON = "session_json"
    CPA_JSON = "cpa_json"


class BrowserProfile(BaseModel):
    """Persisted browser/session hints used for upstream ChatGPT Web calls."""

    session_token: str | None = None
    user_agent: str | None = None
    impersonate_browser: str | None = None
    oai_device_id: str | None = None
    sec_ch_ua: str | None = None
    sec_ch_ua_mobile: str | None = None
    sec_ch_ua_platform: str | None = None


class AccountRecord(BaseModel):
    """Persisted account state tracked in the control database."""

    name: str
    access_token: str
    refresh_token: str | None = None
    source_kind: AccountSourceKind = AccountSourceKind.TOKEN
    email: str | None = None
    user_id: str | None = None
    plan_type: str | None = None
    default_model_slug: str | None = None
    status: str = "active"
    quota_remaining: int = 0
    quota_known: bool = False
    restore_at: str | None = None
    last_refresh_at: int | None = None
    last_used_at: int | None = None
    last_error: str | None = None
    success_count: int = 0
    fail_count: int = 0
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None
    browser_profile_json: str = "{}"

    def browser_profile(self) -> BrowserProfile:
        """Deserializes the persisted browser profile JSON."""
        try:
            return BrowserProfile.model_validate_json(self.browser_profile_json)
        except Exception:
            return BrowserProfile()

    @classmethod
    def minimal(cls, name: str, access_token: str) -> "AccountRecord":
        return cls(name=name, access_token=access_token)


class ApiKeyRecord(BaseModel):
    """Persisted downstream API-key record."""

    id: str
    name: str
    secret_hash: str
    secret_plaintext: str | None = None
    status: str = "active"
    quota_total_calls: int = 0
    quota_used_calls: int = 0
    route_strategy: str = "auto"
    account_group_id: str | None = None
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None

    @classmethod
    def minimal(cls, id: str, name: str, quota_total_calls: int) -> "ApiKeyRecord":
        return cls(id=id, name=name, secret_hash="hash", quota_total_calls=quota_total_calls)


class RouteStrategy(str, Enum):
    """Route policy used by downstream API keys."""

    AUTO = "auto"
    FIXED = "fixed"


class AccountRouteCandidate(BaseModel):
    """Lightweight routing candidate state used during account selection."""

    name: str
    quota_remaining: int
    quota_known: bool
    last_routed_at_ms: int = 0


class AccountMetadata(BaseModel):
    """Refreshed upstream metadata for one imported account."""

    email: str | None = None
    user_id: str | None = None
    plan_type: str | None = None
    default_model_slug: str | None = None
    quota_remaining: int = 0
    quota_known: bool = False
    restore_at: str | None = None


class UsageEventRecord(BaseModel):
    """One usage-event summary written to the database."""

    event_id: str
    request_id: str
    key_id: str
    key_name: str
    account_name: str
    endpoint: str
    requested_model: str
    resolved_upstream_model: str
    requested_n: int
    generated_n: int
    billable_images: int
    status_code: int
    latency_ms: int
    error_code: str | None = None
    error_message: str | None = None
    detail_ref: str | None = None
    created_at: int


class GeneratedImageItem(BaseModel):
    """One downloaded upstream image payload."""

    b64_json: str
    revised_prompt: str = ""


class ChatgptImageResult(BaseModel):
    """Successful upstream image generation result."""

    created: int
    data: list[GeneratedImageItem]
    resolved_model: str


class ChatgptTextResult(BaseModel):
    """Successful upstream text completion result."""

    created: int
    text: str
    resolved_model: str


class ApiKeyCreate(BaseModel):
    """Mutable API-key fields allowed through the admin create surface."""

    name: str
    quota_total_calls: int
    status: str | None = "active"
    route_strategy: str = "auto"
    account_group_id: str | None = None
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None


class ApiKeyUpdate(BaseModel):
    """Mutable API-key fields allowed through the admin update surface."""

    name: str | None = None
    status: str | None = None
    quota_total_calls: int | None = None
    route_strategy: str | None = None
    account_group_id: str | None = None
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None


class ApiKeySecretRecord(BaseModel):
    """One admin-visible API-key record plus the stored plaintext secret."""

    key: ApiKeyRecord
    secret_plaintext: str


class AccountUpdate(BaseModel):
    """Mutable account fields allowed through the admin update surface."""

    plan_type: str | None = None
    status: str | None = None
    quota_remaining: int | None = None
    restore_at: str | None = None
    browser_profile: BrowserProfile | None = None
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None


class ImageEditInput(BaseModel):
    """Image edit input used by the public service layer."""

    image_data: bytes
    file_name: str
    mime_type: str
