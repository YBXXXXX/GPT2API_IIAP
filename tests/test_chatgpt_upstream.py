#!/usr/bin/env python3
"""Tests for ChatGPT Web upstream payload construction."""

from __future__ import annotations

import json

from upstream.chatgpt import ChatgptUpstreamClient


class DummyResponse:
    def __init__(self, status_code: int = 200, data=None, text: str | None = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._data = data or {}
        self.text = text if text is not None else json.dumps(self._data)
        self.content = content

    def json(self):
        return self._data


class RecordingSession:
    def __init__(self) -> None:
        self.posts = []
        self.puts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/backend-api/files"):
            return DummyResponse(data={"file_id": "file-123", "upload_url": "https://upload.local/file-123"})
        if url.endswith("/backend-api/files/file-123/uploaded"):
            return DummyResponse(data={"ok": True})
        if url.endswith("/backend-api/conversation"):
            return DummyResponse(text='data: {"conversation_id":"conv-123"}\n\ndata: [DONE]\n')
        return DummyResponse()

    def put(self, url, **kwargs):
        self.puts.append((url, kwargs))
        return DummyResponse(status_code=204)


def test_upload_image_for_edit_returns_normalized_attachment() -> None:
    client = ChatgptUpstreamClient()
    session = RecordingSession()

    attachment = client._upload_image_for_edit(
        session,
        {"authorization": "Bearer token", "content-type": "application/json"},
        b"image-bytes",
        "cat.png",
        "image/png",
    )

    assert attachment == {
        "id": "file-123",
        "name": "cat.png",
        "mimeType": "image/png",
        "size": len(b"image-bytes"),
        "assetPointer": "file-service://file-123",
    }
    assert session.posts[0][1]["json"]["use_case"] == "multimodal"
    assert session.puts[0][1]["data"] == b"image-bytes"


def test_send_conversation_defaults_to_text_payload() -> None:
    client = ChatgptUpstreamClient()
    session = RecordingSession()

    conv_id = client._send_conversation(
        session,
        {"authorization": "Bearer token"},
        "chat-token",
        None,
        "draw a cat",
        "gpt-image-1",
        "device-id",
    )

    assert conv_id == "conv-123"
    payload = session.posts[-1][1]["json"]
    message = payload["messages"][0]
    assert message["content"] == {"content_type": "text", "parts": ["draw a cat"]}
    assert message["metadata"] == {"attachments": []}


def test_send_conversation_uses_multimodal_payload_for_attachment() -> None:
    client = ChatgptUpstreamClient()
    session = RecordingSession()

    conv_id = client._send_conversation(
        session,
        {"authorization": "Bearer token"},
        "chat-token",
        None,
        "add sunglasses",
        "gpt-image-1",
        "device-id",
        attachment={
            "id": "file-123",
            "name": "cat.png",
            "mimeType": "image/png",
            "size": 11,
            "assetPointer": "file-service://file-123",
        },
    )

    assert conv_id == "conv-123"
    payload = session.posts[-1][1]["json"]
    message = payload["messages"][0]
    assert message["content"]["content_type"] == "multimodal_text"
    parts = message["content"]["parts"]
    image_part = next(p for p in parts if isinstance(p, dict))
    assert image_part["content_type"] == "image_asset_pointer"
    assert image_part["asset_pointer"] == "file-service://file-123"
    assert image_part["size_bytes"] == 11
    assert "add sunglasses" in parts
    assert message["metadata"]["attachments"][0]["id"] == "file-123"
    assert message["metadata"]["attachments"][0]["mime_type"] == "image/png"
