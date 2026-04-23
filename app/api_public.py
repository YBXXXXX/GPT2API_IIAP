#!/usr/bin/env python3
"""Public OpenAI-compatible image endpoints (migrated from Rust src/http/public_api.rs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile

from app.models import ChatgptImageResult
from app.queue_manager import GenerationJob
from app.schemas import (
    ChatCompletionRequest,
    ImageGenerationRequest,
    ResponseRequest,
)
from app.service import AppService, Disabled, ImageEditInput, InvalidKey, QuotaExhausted

router = APIRouter()


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def authenticate_key(service: AppService, authorization: str | None) -> Any:
    token = extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="invalid_key")
    try:
        return service.authenticate_public_key(token)
    except InvalidKey:
        raise HTTPException(status_code=401, detail="invalid_key")
    except Disabled:
        raise HTTPException(status_code=403, detail="disabled")
    except QuotaExhausted:
        raise HTTPException(status_code=403, detail="quota_exhausted")


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, str]:
    return {"version": "0.1.0"}


@router.get("/v1/models")
async def list_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "auto", "object": "model", "created": 0, "owned_by": "GPT2API_IIAP"},
            {"id": "gpt-5", "object": "model", "created": 0, "owned_by": "GPT2API_IIAP"},
            {"id": "gpt-5-mini", "object": "model", "created": 0, "owned_by": "GPT2API_IIAP"},
            {"id": "gpt-image-1", "object": "model", "created": 0, "owned_by": "GPT2API_IIAP"},
            {"id": "gpt-image-2", "object": "model", "created": 0, "owned_by": "GPT2API_IIAP"},
        ],
    }


@router.get("/auth/login")
@router.post("/auth/login")
async def login(
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    key = await authenticate_key(service, authorization)
    return {
        "ok": True,
        "version": "0.1.0",
        "key": {
            "id": key.id,
            "name": key.name,
            "status": key.status,
            "quota_total_calls": key.quota_total_calls,
            "quota_used_calls": key.quota_used_calls,
            "route_strategy": key.route_strategy,
        },
    }


# ------------------------------------------------------------------ #
# Queue status
# ------------------------------------------------------------------ #

@router.get("/v1/queue/status")
async def queue_status(request: Request) -> dict[str, Any]:
    """Return current queue length and processing count."""
    queue = request.app.state.queue
    return queue.get_status()


@router.get("/v1/queue/result/{request_id}")
async def queue_result(request_id: str, request: Request) -> dict[str, Any]:
    """Poll for result of a queued generation request."""
    queue = request.app.state.queue
    result = queue.get_result(request_id)
    if result is None:
        position = queue.get_position(request_id)
        return {"status": "pending", "position": position}
    return result


# ------------------------------------------------------------------ #
# Image generation (queued)
# ------------------------------------------------------------------ #

@router.post("/v1/images/generations")
async def generate_images(
    request: Request,
    body: ImageGenerationRequest,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    # Optional API key auth: validate & deduct quota if provided, otherwise allow anonymous
    if authorization:
        key = await authenticate_key(service, authorization)
        ensure_key_can_consume(key, body.n)

    queue = request.app.state.queue
    job = GenerationJob(
        prompt=body.prompt.strip(),
        model=body.model.strip(),
        n=max(1, min(body.n, 4)),
    )
    request_id = await queue.submit(job)
    return {"request_id": request_id, "status": "queued"}


@router.post("/v1/images/edits")
async def edit_images(
    request: Request,
    prompt: str = Form(...),
    model: str = Form("gpt-image-1"),
    n: int = Form(1),
    image: UploadFile | None = File(None),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    service: AppService = request.app.state.service
    key = await authenticate_key(service, authorization)
    if image is None:
        raise HTTPException(status_code=400, detail="image file is required")
    image_data = await image.read()
    if not image_data:
        raise HTTPException(status_code=400, detail="image file is required")
    edit_input = ImageEditInput(
        image_data=image_data,
        file_name=image.filename or "image.png",
        mime_type=image.content_type or "image/png",
    )
    try:
        result = await service.edit_images_for_key(
            key, prompt.strip(), model.strip(), max(1, min(n, 4)), edit_input
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return _image_result_to_json(result)


@router.post("/v1/chat/completions")
async def create_chat_completion(
    request: Request,
    body: ChatCompletionRequest,
    authorization: str | None = Header(None),
) -> Any:
    service: AppService = request.app.state.service
    key = await authenticate_key(service, authorization)
    # TODO: implement text chat completions and streaming
    raise HTTPException(status_code=501, detail="chat completions not yet implemented")


@router.post("/v1/responses")
async def create_response(
    request: Request,
    body: ResponseRequest,
    authorization: str | None = Header(None),
) -> Any:
    service: AppService = request.app.state.service
    key = await authenticate_key(service, authorization)
    # TODO: implement responses API
    raise HTTPException(status_code=501, detail="responses API not yet implemented")


def _image_result_to_json(result: ChatgptImageResult) -> dict[str, Any]:
    return {
        "created": result.created,
        "data": [
            {"b64_json": item.b64_json, "revised_prompt": item.revised_prompt}
            for item in result.data
        ],
    }


def ensure_key_can_consume(key: Any, cost: int) -> None:
    if key.status != "active":
        raise HTTPException(status_code=403, detail="disabled")
    if cost <= 0:
        return
    if key.quota_total_calls <= 0 or key.quota_used_calls + cost > key.quota_total_calls:
        raise HTTPException(status_code=403, detail="quota_exhausted")
