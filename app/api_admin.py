#!/usr/bin/env python3
"""Admin management endpoints (migrated from Rust src/http/admin_api.rs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.models import AccountUpdate, ApiKeyCreate, ApiKeyUpdate, BrowserProfile
from app.schemas import (
    CreateKeyRequest,
    DeleteAccountsRequest,
    ImportAccountsRequest,
    ImportSub2apiRequest,
    RefreshAccountsRequest,
    UpdateAccountRequest,
    UpdateKeyRequest,
)
from app.service import AppService

router = APIRouter(prefix="/admin")


def require_admin(headers: dict[str, str | None], service: AppService) -> None:
    auth = headers.get("authorization") or ""
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not service.is_admin_token(token):
        raise HTTPException(status_code=401, detail="authorization is invalid")


@router.get("/status")
async def admin_status(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    accounts = service.storage.list_accounts()
    outbox = service.storage.list_pending_outbox()
    return {
        "accounts_total": len(accounts),
        "accounts_active": sum(1 for a in accounts if a.status == "active"),
        "accounts_limited": sum(1 for a in accounts if a.status == "limited"),
        "accounts_invalid": sum(1 for a in accounts if a.status == "invalid"),
        "outbox_backlog": len(outbox),
    }


@router.get("/accounts")
async def list_accounts(
    request: Request,
    authorization: str | None = Header(None),
) -> list[Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    accounts = service.storage.list_accounts()
    return [a.model_dump() for a in accounts]


@router.post("/accounts/import")
async def import_accounts(
    request: Request,
    body: ImportAccountsRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    items: list[tuple[str, str]] = []
    for token in body.access_tokens:
        token = token.strip()
        if token:
            items.append(("token", token))
    for sj in body.session_jsons:
        sj = sj.strip()
        if sj:
            items.append(("session_json", sj))
    if not items:
        raise HTTPException(status_code=400, detail="access_tokens or session_jsons is required")
    try:
        imported = service.import_accounts(items)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    access_tokens = [a.access_token for a in imported]
    refreshed = await service.refresh_accounts(access_tokens)
    return {"items": [a.model_dump() for a in refreshed]}


@router.post("/accounts/import-sub2api")
async def import_sub2api_accounts(
    request: Request,
    body: ImportSub2apiRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Import accounts from sub2api JSON export file."""
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    import json

    try:
        data = json.loads(body.accounts_json)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {e}")
    imported = service.import_sub2api_accounts(data)
    if body.auto_refresh_metadata:
        access_tokens = [a.access_token for a in imported]
        refreshed = await service.refresh_accounts(access_tokens)
        return {"imported_count": len(imported), "items": [a.model_dump() for a in refreshed]}
    return {"imported_count": len(imported), "items": [a.model_dump() for a in imported]}


@router.delete("/accounts")
async def delete_accounts(
    request: Request,
    body: DeleteAccountsRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    tokens = list(body.access_tokens)
    tokens.extend(body.tokens)
    tokens = [t.strip() for t in tokens if t.strip()]
    if not tokens:
        raise HTTPException(status_code=400, detail="access_tokens is required")
    items = service.delete_accounts(tokens)
    return {"items": [a.model_dump() for a in items]}


@router.post("/accounts/refresh")
async def refresh_accounts(
    request: Request,
    body: RefreshAccountsRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    tokens = [t.strip() for t in body.access_tokens if t.strip()]
    items = await service.refresh_accounts(tokens or None)
    return {"items": [a.model_dump() for a in items]}


@router.post("/accounts/update")
async def update_account(
    request: Request,
    body: UpdateAccountRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    access_token = body.access_token.strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="access_token is required")
    browser_profile = None
    if body.session_token or body.user_agent or body.impersonate_browser:
        browser_profile = BrowserProfile(
            session_token=body.session_token,
            user_agent=body.user_agent,
            impersonate_browser=body.impersonate_browser,
        )
    update = AccountUpdate(
        plan_type=body.plan_type,
        status=body.status,
        quota_remaining=body.quota_remaining,
        restore_at=body.restore_at,
        browser_profile=browser_profile,
        request_max_concurrency=body.request_max_concurrency,
        request_min_start_interval_ms=body.request_min_start_interval_ms,
    )
    account = service.update_account(access_token, update)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {"item": account.model_dump()}


@router.get("/keys")
async def list_keys(
    request: Request,
    authorization: str | None = Header(None),
) -> list[Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    keys = service.storage.list_api_keys()
    return [k.model_dump() for k in keys]


@router.post("/keys")
async def create_key(
    request: Request,
    body: CreateKeyRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    try:
        created = service.create_api_key(
            ApiKeyCreate(
                name=body.name,
                quota_total_calls=body.quota_total_calls,
                status=body.status,
                route_strategy=body.route_strategy,
                account_group_id=body.account_group_id,
                request_max_concurrency=body.request_max_concurrency,
                request_min_start_interval_ms=body.request_min_start_interval_ms,
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _serialize_key_record(created.key, include_secret=True)


@router.patch("/keys/{key_id}")
async def update_key(
    request: Request,
    key_id: str,
    body: UpdateKeyRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    try:
        key = service.update_api_key(
            key_id,
            ApiKeyUpdate(
                name=body.name,
                status=body.status,
                quota_total_calls=body.quota_total_calls,
                route_strategy=body.route_strategy,
                account_group_id=body.account_group_id,
                request_max_concurrency=body.request_max_concurrency,
                request_min_start_interval_ms=body.request_min_start_interval_ms,
            ),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if key is None:
        raise HTTPException(status_code=404, detail="key not found")
    return _serialize_key(key, None)


@router.post("/keys/{key_id}/rotate")
async def rotate_key(
    request: Request,
    key_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    rotated = service.rotate_api_key(key_id)
    if rotated is None:
        raise HTTPException(status_code=404, detail="key not found")
    return _serialize_key_record(rotated.key, include_secret=True)


@router.delete("/keys/{key_id}")
async def delete_key(
    request: Request,
    key_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    if not service.delete_api_key(key_id):
        raise HTTPException(status_code=404, detail="key not found")
    return {"ok": True}


@router.get("/usage")
async def list_usage(
    request: Request,
    limit: int = Query(50, ge=1),
    authorization: str | None = Header(None),
) -> list[Any]:
    service: AppService = request.app.state.service
    require_admin({"authorization": authorization}, service)
    # TODO: implement usage query from SQLite usage_events
    conn = service.storage._connect()
    cur = conn.execute(
        """
        SELECT event_id, request_id, key_id, key_name, account_name, endpoint,
               requested_model, resolved_upstream_model, requested_n, generated_n,
               billable_images, status_code, latency_ms, error_code, error_message,
               detail_ref, created_at
        FROM usage_events
        ORDER BY created_at DESC, event_id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "event_id": r[0],
            "request_id": r[1],
            "key_id": r[2],
            "key_name": r[3],
            "account_name": r[4],
            "endpoint": r[5],
            "requested_model": r[6],
            "resolved_upstream_model": r[7],
            "requested_n": r[8],
            "generated_n": r[9],
            "billable_images": r[10],
            "status_code": r[11],
            "latency_ms": r[12],
            "error_code": r[13],
            "error_message": r[14],
            "detail_ref": r[15],
            "created_at": r[16],
        }
        for r in rows
    ]


def _serialize_key_record(record: Any, include_secret: bool = False) -> dict[str, Any]:
    return _serialize_key(record, record.secret_plaintext if include_secret else None)


def _serialize_key(key: Any, secret_plaintext: str | None = None) -> dict[str, Any]:
    plaintext = secret_plaintext or key.secret_plaintext
    return {
        "id": key.id,
        "name": key.name,
        "secret_hash": key.secret_hash,
        "status": key.status,
        "quota_total_calls": key.quota_total_calls,
        "quota_used_calls": key.quota_used_calls,
        "route_strategy": key.route_strategy,
        "account_group_id": key.account_group_id,
        "request_max_concurrency": key.request_max_concurrency,
        "request_min_start_interval_ms": key.request_min_start_interval_ms,
        "secret_plaintext": plaintext,
    }
