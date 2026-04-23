#!/usr/bin/env python3
"""Request/response schemas for public and admin APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# Public API schemas
# ------------------------------------------------------------------ #

class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str = "gpt-image-1"
    n: int = Field(default=1, ge=1, le=4)


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    stream: bool = False
    n: int = Field(default=1, ge=1, le=4)


class ResponseRequest(BaseModel):
    model: str = "gpt-5"
    input: Any = None
    stream: bool = False


# ------------------------------------------------------------------ #
# Admin API schemas
# ------------------------------------------------------------------ #

class ImportAccountsRequest(BaseModel):
    access_tokens: list[str] = Field(default_factory=list)
    session_jsons: list[str] = Field(default_factory=list)


class ImportSub2apiRequest(BaseModel):
    """Import accounts from sub2api JSON export."""

    accounts_json: str = Field(default="")
    auto_refresh_metadata: bool = Field(default=True)


class DeleteAccountsRequest(BaseModel):
    access_tokens: list[str] = Field(default_factory=list)
    tokens: list[str] = Field(default_factory=list)


class RefreshAccountsRequest(BaseModel):
    access_tokens: list[str] = Field(default_factory=list)


class UpdateAccountRequest(BaseModel):
    access_token: str
    plan_type: str | None = None
    status: str | None = None
    quota_remaining: int | None = None
    restore_at: str | None = None
    session_token: str | None = None
    user_agent: str | None = None
    impersonate_browser: str | None = None
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None


class CreateKeyRequest(BaseModel):
    name: str
    quota_total_calls: int
    status: str | None = "active"
    route_strategy: str = "auto"
    account_group_id: str | None = None
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None


class UpdateKeyRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    quota_total_calls: int | None = None
    route_strategy: str | None = None
    account_group_id: str | None = None
    request_max_concurrency: int | None = None
    request_min_start_interval_ms: int | None = None


class UsageQuery(BaseModel):
    limit: int = 50
