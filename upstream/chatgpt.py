#!/usr/bin/env python3
"""ChatGPT Web transport helpers (migrated from Rust src/upstream/chatgpt.rs)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import time
import uuid
from typing import Any

from curl_cffi import requests as curl_requests

from app.models import (
    AccountRecord,
    ChatgptImageResult,
    ChatgptTextResult,
    GeneratedImageItem,
)


class ChatgptUpstreamClient:
    """ChatGPT Web transport client."""

    def __init__(self, base_url: str = "https://chatgpt.com", proxy_url: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.proxy_url = proxy_url

    # ------------------------------------------------------------------ #
    # Public async interfaces
    # ------------------------------------------------------------------ #

    async def fetch_account_metadata(self, account: AccountRecord) -> dict[str, Any]:
        """Fetches account metadata from /backend-api/me and /backend-api/conversation/init."""
        return await asyncio.get_running_loop().run_in_executor(
            None, self._sync_fetch_account_metadata, account
        )

    async def generate_image(
        self, account: AccountRecord, prompt: str, requested_model: str
    ) -> ChatgptImageResult:
        """Executes one text-to-image request against ChatGPT Web."""
        return await asyncio.get_running_loop().run_in_executor(
            None, self._sync_generate_image, account, prompt, requested_model
        )

    async def edit_image(
        self,
        account: AccountRecord,
        prompt: str,
        requested_model: str,
        image_data: bytes,
        file_name: str,
        mime_type: str,
    ) -> ChatgptImageResult:
        """Executes one image-edit request against ChatGPT Web."""
        return await asyncio.get_running_loop().run_in_executor(
            None, self._sync_edit_image, account, prompt, requested_model, image_data, file_name, mime_type
        )

    async def complete_text(
        self, account: AccountRecord, prompt: str, requested_model: str
    ) -> ChatgptTextResult:
        """Executes one text completion request against ChatGPT Web."""
        raise NotImplementedError("complete_text not yet implemented")

    async def start_text_stream(
        self, account: AccountRecord, prompt: str, requested_model: str
    ) -> dict[str, Any]:
        """Opens one streaming text completion against ChatGPT Web."""
        raise NotImplementedError("start_text_stream not yet implemented")

    # ------------------------------------------------------------------ #
    # Synchronous implementations (run inside thread pool)
    # ------------------------------------------------------------------ #

    def _sync_fetch_account_metadata(self, account: AccountRecord) -> dict[str, Any]:
        """Sync version: fetch /backend-api/me and /backend-api/conversation/init."""
        session, headers = self._build_session_and_headers(account)
        device_id = str(uuid.uuid4())

        # Bootstrap to warm cookies/session
        self._bootstrap(session, headers)

        # /backend-api/me
        me_resp = session.get(
            f"{self.base_url}/backend-api/me",
            headers={**headers, "oai-device-id": device_id},
            timeout=30,
        )
        me_data = me_resp.json() if me_resp.status_code == 200 else {}

        # /backend-api/conversation/init
        init_resp = session.post(
            f"{self.base_url}/backend-api/conversation/init",
            headers={**headers, "content-type": "application/json", "oai-device-id": device_id},
            json={
                "gizmo_id": None,
                "requested_default_model": None,
                "conversation_id": None,
                "timezone_offset_min": -480,
            },
            timeout=30,
        )
        init_data = init_resp.json() if init_resp.status_code == 200 else {}

        limits = init_data.get("limits_progress", [])
        image_limit = next((l for l in limits if l.get("feature_name") == "image_gen"), None)

        return {
            "email": me_data.get("email"),
            "user_id": me_data.get("id"),
            "plan_type": me_data.get("plan_type"),
            "default_model_slug": init_data.get("default_model_slug"),
            "quota_remaining": image_limit.get("remaining") if image_limit else None,
            "reset_after": image_limit.get("reset_after") if image_limit else None,
        }

    def _sync_generate_image(
        self, account: AccountRecord, prompt: str, requested_model: str
    ) -> ChatgptImageResult:
        """Sync version: full image generation flow."""
        session, headers = self._build_session_and_headers(account)

        # Step 1: bootstrap
        scripts, build_id = self._bootstrap(session, headers)

        device_id = str(uuid.uuid4())
        req_headers = {
            **headers,
            "content-type": "application/json",
            "oai-device-id": device_id,
        }

        # Step 2: chat requirements
        chat_token, pow_info = self._chat_requirements(session, req_headers)

        # Step 3: PoW
        proof_token = None
        if pow_info.get("required"):
            proof_token = self._generate_proof_token(
                pow_info.get("seed", ""),
                pow_info.get("difficulty", ""),
                scripts,
                build_id,
            )

        # Step 4: send conversation (non-streaming to avoid HTTP/2 issues)
        conv_id = self._send_conversation(
            session, req_headers, chat_token, proof_token, prompt, requested_model, device_id
        )

        # Step 5: poll for image file IDs
        file_ids = self._poll_for_image_ids(session, req_headers, conv_id)

        if not file_ids:
            raise RuntimeError("no file IDs found after polling")

        # Step 6: download images
        images: list[GeneratedImageItem] = []
        for fid in set(file_ids):
            img_bytes = self._download_image(session, req_headers, conv_id, fid)
            if img_bytes:
                b64 = base64.b64encode(img_bytes).decode()
                images.append(GeneratedImageItem(b64_json=b64, revised_prompt=prompt))

        if not images:
            raise RuntimeError("failed to download any images")

        return ChatgptImageResult(
            created=int(time.time()),
            data=images,
            resolved_model=requested_model,
        )

    def _sync_edit_image(
        self,
        account: AccountRecord,
        prompt: str,
        requested_model: str,
        image_data: bytes,
        file_name: str,
        mime_type: str,
    ) -> ChatgptImageResult:
        """Sync version: upload input image then run the standard generation flow."""
        session, headers = self._build_session_and_headers(account)

        scripts, build_id = self._bootstrap(session, headers)

        device_id = str(uuid.uuid4())
        req_headers = {
            **headers,
            "content-type": "application/json",
            "oai-device-id": device_id,
        }

        chat_token, pow_info = self._chat_requirements(session, req_headers)

        proof_token = None
        if pow_info.get("required"):
            proof_token = self._generate_proof_token(
                pow_info.get("seed", ""),
                pow_info.get("difficulty", ""),
                scripts,
                build_id,
            )

        attachment = self._upload_image_for_edit(session, req_headers, image_data, file_name, mime_type)

        conv_id = self._send_conversation(
            session, req_headers, chat_token, proof_token, prompt, requested_model, device_id,
            attachment=attachment,
        )

        file_ids = self._poll_for_image_ids(session, req_headers, conv_id)

        if not file_ids:
            raise RuntimeError("no file IDs found after polling")

        images: list[GeneratedImageItem] = []
        for fid in set(file_ids):
            img_bytes = self._download_image(session, req_headers, conv_id, fid)
            if img_bytes:
                b64 = base64.b64encode(img_bytes).decode()
                images.append(GeneratedImageItem(b64_json=b64, revised_prompt=prompt))

        if not images:
            raise RuntimeError("failed to download any images")

        return ChatgptImageResult(
            created=int(time.time()),
            data=images,
            resolved_model=requested_model,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _upload_image_for_edit(
        self,
        session: curl_requests.Session,
        headers: dict[str, str],
        image_data: bytes,
        file_name: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """Upload an image to ChatGPT Web and return a normalized attachment dict."""
        upload_headers = {k: v for k, v in headers.items() if k != "content-type"}

        # Step 1: request an upload slot
        create_resp = session.post(
            f"{self.base_url}/backend-api/files",
            headers=upload_headers,
            json={
                "file_name": file_name,
                "file_size": len(image_data),
                "mime_type": mime_type,
                "use_case": "multimodal",
            },
            timeout=30,
        )
        if create_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"image upload slot request failed: HTTP {create_resp.status_code} {create_resp.text[:400]}"
            )
        create_data = create_resp.json()
        file_id = create_data.get("file_id") or create_data.get("id")
        upload_url = create_data.get("upload_url")
        if not file_id or not upload_url:
            raise RuntimeError(f"image upload response missing file_id or upload_url: {create_data}")

        # Step 2: PUT image bytes to the signed upload URL
        put_resp = session.put(
            upload_url,
            data=image_data,
            headers={"content-type": mime_type, "x-ms-blob-type": "BlockBlob"},
            timeout=120,
        )
        if put_resp.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"image PUT upload failed: HTTP {put_resp.status_code} {put_resp.text[:400]}"
            )

        # Step 3: mark upload complete
        done_resp = session.post(
            f"{self.base_url}/backend-api/files/{file_id}/uploaded",
            headers=upload_headers,
            json={},
            timeout=30,
        )
        if done_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"image upload completion failed: HTTP {done_resp.status_code} {done_resp.text[:400]}"
            )

        return {
            "id": file_id,
            "name": file_name,
            "mimeType": mime_type,
            "size": len(image_data),
            "assetPointer": f"file-service://{file_id}",
        }

    def _build_session_and_headers(self, account: AccountRecord) -> tuple[curl_requests.Session, dict[str, str]]:
        profile = account.browser_profile()
        impersonate = profile.impersonate_browser or "edge"
        session = curl_requests.Session(impersonate=impersonate)
        if self.proxy_url:
            session.proxies = {"http": self.proxy_url, "https": self.proxy_url}

        ua = profile.user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        headers: dict[str, str] = {
            "authorization": f"Bearer {account.access_token}",
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "origin": self.base_url,
            "referer": f"{self.base_url}/",
            "user-agent": ua,
        }
        if profile.session_token:
            headers["cookie"] = f"__Secure-next-auth.session-token={profile.session_token}"

        return session, headers

    def _bootstrap(
        self, session: curl_requests.Session, headers: dict[str, str]
    ) -> tuple[list[str], str | None]:
        resp = session.get(self.base_url, headers=headers, timeout=30)
        scripts: list[str] = []
        build_id: str | None = None
        for line in resp.text.split("\n"):
            if "<script" in line and "src=" in line:
                start = line.find('src="')
                if start != -1:
                    end = line.find('"', start + 5)
                    if end != -1:
                        scripts.append(line[start + 5 : end])
            if '"buildId"' in line:
                try:
                    data = json.loads(line[line.find("{") : line.rfind("}") + 1])
                    build_id = data.get("buildId")
                except Exception:
                    pass
        return scripts, build_id

    def _chat_requirements(
        self, session: curl_requests.Session, headers: dict[str, str]
    ) -> tuple[str, dict[str, Any]]:
        resp = session.post(
            f"{self.base_url}/backend-api/sentinel/chat-requirements",
            headers=headers,
            json={"conversation_mode_kind": "primary_assistant"},
            timeout=30,
        )
        data = resp.json()
        return data.get("token", ""), data.get("proofofwork", {})

    def _build_pow_config(self, scripts: list[str], build_id: str | None) -> list:
        now = time.time()
        req_id = str(uuid.uuid4())
        nav_keys = [
            "webdriver-false",
            "vendor-Google Inc.",
            "cookieEnabled-true",
            "pdfViewerEnabled-true",
            "hardwareConcurrency-32",
            "language-zh-CN",
            "mimeTypes-[object MimeTypeArray]",
            "userAgentData-[object NavigatorUAData]",
        ]
        doc_keys = ["_reactListening", "location"]
        win_keys = [
            "window", "self", "document", "location", "history",
            "navigator", "screen", "innerWidth", "innerHeight",
            "devicePixelRatio", "chrome", "statusbar", "status",
        ]
        sdk_script = ""
        for s in scripts:
            if "sentinel/sdk.js" in s:
                sdk_script = s
                break
        if not sdk_script:
            sdk_script = f"{self.base_url}/backend-api/sentinel/sdk.js"
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        ts_ms = now * 1000.0
        return [
            3000,
            time.strftime("%a %b %d %Y %H:%M:%S GMT-0500 (Eastern Standard Time)", time.gmtime(now + 5 * 3600)),
            4294705152,
            0,
            ua,
            sdk_script,
            build_id or "",
            "en-US",
            "en-US,es-US,en,es",
            0,
            nav_keys,
            doc_keys,
            win_keys,
            ts_ms,
            req_id,
            "",
            32,
            ts_ms,
        ]

    def _generate_proof_token(
        self, seed: str, difficulty: str, scripts: list[str], build_id: str | None
    ) -> str:
        config = self._build_pow_config(scripts, build_id)
        part1_json = json.dumps(config[:3], separators=(",", ":"))
        part1 = part1_json.rstrip("]") + ","
        part2_json = json.dumps(config[4:9], separators=(",", ":"))
        part2 = "," + part2_json[1:-1] + ","
        part3_json = json.dumps(config[10:], separators=(",", ":"))
        part3 = "," + part3_json[1:]
        target = self._hex_decode(difficulty)

        for i in range(500_000):
            attempt = (
                part1.encode()
                + str(i).encode()
                + part2.encode()
                + str(i >> 1).encode()
                + part3.encode()
            )
            encoded = base64.b64encode(attempt).decode()
            hasher = hashlib.sha3_512()
            hasher.update(seed.encode())
            hasher.update(encoded.encode())
            digest = hasher.digest()
            if digest[: len(target)] <= target:
                return f"gAAAAAB{encoded}"

        fallback = base64.b64encode(f'"{seed}"'.encode()).decode()
        return f"wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D{fallback}"

    @staticmethod
    def _hex_decode(raw: str) -> bytes:
        return bytes(int(raw[i : i + 2], 16) for i in range(0, len(raw), 2))

    def _send_conversation(
        self,
        session: curl_requests.Session,
        headers: dict[str, str],
        chat_token: str,
        proof_token: str | None,
        prompt: str,
        model: str,
        device_id: str,
        attachment: dict[str, Any] | None = None,
    ) -> str:
        seed = random.randint(1, 100_000)
        contextual_info = {
            "is_dark_mode": False,
            "time_since_loaded": 50 + (seed % 450),
            "page_height": 500 + (seed % 500),
            "page_width": 1000 + (seed % 1000),
            "pixel_ratio": 1.2,
            "screen_height": 800 + (seed % 400),
            "screen_width": 1200 + (seed % 1000),
        }
        if attachment:
            image_part = {
                "content_type": "image_asset_pointer",
                "asset_pointer": attachment["assetPointer"],
                "size_bytes": attachment["size"],
                "metadata": {},
            }
            msg_content = {"content_type": "multimodal_text", "parts": [image_part, prompt]}
            msg_metadata = {
                "attachments": [
                    {
                        "id": attachment["id"],
                        "name": attachment["name"],
                        "mimeType": attachment["mimeType"],
                        "mime_type": attachment["mimeType"],
                        "size": attachment["size"],
                        "assetPointer": attachment["assetPointer"],
                    }
                ]
            }
        else:
            msg_content = {"content_type": "text", "parts": [prompt]}
            msg_metadata = {"attachments": []}
        payload = {
            "action": "next",
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "author": {"role": "user"},
                    "content": msg_content,
                    "metadata": msg_metadata,
                }
            ],
            "parent_message_id": str(uuid.uuid4()),
            "model": model,
            "history_and_training_disabled": False,
            "timezone_offset_min": -480,
            "timezone": "America/Los_Angeles",
            "conversation_mode": {"kind": "primary_assistant"},
            "conversation_origin": None,
            "force_paragen": False,
            "force_paragen_model_slug": "",
            "force_rate_limit": False,
            "force_use_sse": True,
            "paragen_cot_summary_display_override": "allow",
            "paragen_stream_type_override": None,
            "reset_rate_limits": False,
            "suggestions": [],
            "supported_encodings": [],
            "system_hints": ["picture_v2"],
            "variant_purpose": "comparison_implicit",
            "websocket_request_id": str(uuid.uuid4()),
            "client_contextual_info": contextual_info,
        }
        conv_headers = {
            **headers,
            "accept": "text/event-stream",
            "content-type": "application/json",
            "oai-language": "zh-CN",
            "oai-client-build-number": "5955942",
            "oai-client-version": "prod-be885abbfcfe7b1f511e88b3003d9ee44757fbad",
            "openai-sentinel-chat-requirements-token": chat_token,
        }
        if proof_token:
            conv_headers["openai-sentinel-proof-token"] = proof_token

        resp = session.post(
            f"{self.base_url}/backend-api/conversation",
            headers=conv_headers,
            json=payload,
            timeout=120,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"conversation failed: HTTP {resp.status_code} {resp.text[:500]}")

        conv_id = ""
        refusal_message = ""
        for line in resp.text.split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]" or not data:
                continue
            try:
                event = json.loads(data)
                if not conv_id:
                    conv_id = event.get("conversation_id", "")
                text = self._extract_message_text(event.get("message") or {})
                if text and self._looks_like_refusal(text):
                    refusal_message = text
            except json.JSONDecodeError:
                continue

        if refusal_message:
            raise RuntimeError(refusal_message)
        if not conv_id:
            raise RuntimeError("no conversation_id in SSE response")
        return conv_id

    def _poll_for_image_ids(
        self, session: curl_requests.Session, headers: dict[str, str], conv_id: str
    ) -> list[str]:
        deadline = time.time() + 120
        file_ids: list[str] = []
        last_processing_message: str | None = None
        last_refusal_message: str | None = None
        while time.time() < deadline:
            resp = session.get(
                f"{self.base_url}/backend-api/conversation/{conv_id}",
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                file_ids, processing_message, refusal_message = self._extract_image_poll_state(data)
                if file_ids:
                    return list(dict.fromkeys(file_ids))
                if refusal_message:
                    raise RuntimeError(refusal_message)
                if processing_message:
                    last_processing_message = processing_message
            time.sleep(3)
        if last_refusal_message:
            raise RuntimeError(last_refusal_message)
        if last_processing_message:
            raise RuntimeError(f"image generation timed out while still processing: {last_processing_message}")
        return file_ids

    def _extract_image_poll_state(self, data: dict[str, Any]) -> tuple[list[str], str | None, str | None]:
        mapping = data.get("mapping", {})
        file_ids: list[str] = []
        processing_message: str | None = None
        refusal_message: str | None = None

        for node in mapping.values():
            msg = node.get("message") or {}
            if not msg:
                continue
            role = msg.get("author", {}).get("role")
            metadata = msg.get("metadata", {}) or {}
            content = msg.get("content", {}) or {}
            content_type = content.get("content_type")
            parts = content.get("parts", []) if isinstance(content.get("parts"), list) else []

            metadata_file_ids = metadata.get("file_ids")
            if isinstance(metadata_file_ids, list):
                for fid in metadata_file_ids:
                    if isinstance(fid, str) and fid:
                        file_ids.append(fid)

            for part in parts:
                if isinstance(part, dict):
                    pointer = part.get("asset_pointer", "")
                    if pointer.startswith("sediment://"):
                        file_ids.append(pointer[11:])
                    elif pointer.startswith("file-service://"):
                        file_ids.append(pointer[15:])

            text_parts = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
            text = "\n".join(text_parts)
            lower_text = text.lower()

            if role == "tool":
                if metadata.get("async_task_type") == "image_gen" and file_ids:
                    continue
                if metadata.get("image_gen_async") or metadata.get("image_gen_task_id"):
                    if text:
                        processing_message = text
                if any(keyword in lower_text for keyword in ("正在处理图片", "processing", "creating images")):
                    processing_message = text or processing_message

            if role == "assistant" and text:
                if self._looks_like_refusal(text):
                    refusal_message = text

        return file_ids, processing_message, refusal_message

    @staticmethod
    def _extract_message_text(message: dict[str, Any]) -> str:
        content = message.get("content", {}) or {}
        parts = content.get("parts", []) if isinstance(content.get("parts"), list) else []
        text_parts = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
        return "\n".join(text_parts)

    @staticmethod
    def _looks_like_refusal(text: str) -> bool:
        lower_text = text.lower()
        return any(keyword in text for keyword in ("无法", "不能", "抱歉", "对不起", "防护限制", "违反")) or any(
            keyword in lower_text
            for keyword in ("i can't", "i cannot", "sorry", "unable to", "safety policy", "policy")
        )

    def _download_image(
        self,
        session: curl_requests.Session,
        headers: dict[str, str],
        conv_id: str,
        file_id: str,
    ) -> bytes | None:
        dl_url = f"{self.base_url}/backend-api/conversation/{conv_id}/attachment/{file_id}/download"
        dl_resp = session.get(dl_url, headers=headers, timeout=30)
        if dl_resp.status_code != 200:
            return None
        dl_data = dl_resp.json()
        url = dl_data.get("download_url", "")
        if not url:
            return None
        img_resp = session.get(url, timeout=60)
        if img_resp.status_code == 200:
            return img_resp.content
        return None
