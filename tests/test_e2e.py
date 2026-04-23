#!/usr/bin/env python3
"""End-to-end test against real ChatGPT Web upstream."""

from __future__ import annotations

import base64
import json
import time

import pytest
from curl_cffi import requests as curl_requests

from app.config import settings
from app.models import AccountRecord, BrowserProfile
from upstream.chatgpt import ChatgptUpstreamClient


@pytest.fixture
def test_account() -> AccountRecord:
    """Build a test account from the .env credentials."""
    if not settings.openai_access_token:
        pytest.skip("OPENAI_ACCESS_TOKEN not set in .env")
    return AccountRecord(
        name="test_account",
        access_token=settings.openai_access_token,
        browser_profile_json=BrowserProfile(
            session_token=settings.openai_session_token,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            impersonate_browser="edge",
        ).model_dump_json(),
    )


@pytest.fixture
def upstream_client() -> ChatgptUpstreamClient:
    return ChatgptUpstreamClient(
        base_url=settings.chatgpt_base_url,
        proxy_url=settings.upstream_proxy,
    )


class TestTokenValidity:
    """Verify the provided tokens can authenticate with ChatGPT Web."""

    def test_fetch_account_metadata(self, test_account: AccountRecord, upstream_client: ChatgptUpstreamClient) -> None:
        """Test /backend-api/me to check token validity."""
        pytest.skip("fetch_account_metadata not yet implemented in upstream/chatgpt.py")


class TestDirectUpstream:
    """Direct HTTP tests against ChatGPT Web (bypassing our upstream skeleton)."""

    def test_me_endpoint(self, test_account: AccountRecord) -> None:
        """Directly call /backend-api/me to verify token."""
        proxy = settings.upstream_proxy
        profile = test_account.browser_profile()

        # Use curl_cffi with browser impersonation
        impersonate = profile.impersonate_browser or "edge"
        session = curl_requests.Session(impersonate=impersonate)
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        headers = {
            "authorization": f"Bearer {test_account.access_token}",
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "referer": "https://chatgpt.com/",
        }
        if profile.session_token:
            headers["cookie"] = f"__Secure-next-auth.session-token={profile.session_token}"

        response = session.get(
            f"{settings.chatgpt_base_url}/backend-api/me",
            headers=headers,
            timeout=30,
        )
        print(f"/backend-api/me status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Email: {data.get('email')}")
            print(f"User ID: {data.get('id')}")
            assert data.get("email") is not None
        else:
            print(f"Response body: {response.text[:500]}")
            pytest.fail(f"/backend-api/me returned {response.status_code}")

    def test_conversation_init(self, test_account: AccountRecord) -> None:
        """Directly call /backend-api/conversation/init to check quota."""
        proxy = settings.upstream_proxy
        profile = test_account.browser_profile()

        impersonate = profile.impersonate_browser or "edge"
        session = curl_requests.Session(impersonate=impersonate)
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        headers = {
            "authorization": f"Bearer {test_account.access_token}",
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "referer": "https://chatgpt.com/",
            "content-type": "application/json",
        }
        if profile.session_token:
            headers["cookie"] = f"__Secure-next-auth.session-token={profile.session_token}"

        response = session.post(
            f"{settings.chatgpt_base_url}/backend-api/conversation/init",
            headers=headers,
            json={
                "gizmo_id": None,
                "requested_default_model": None,
                "conversation_id": None,
                "timezone_offset_min": -480,
            },
            timeout=30,
        )
        print(f"/backend-api/conversation/init status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            limits = data.get("limits_progress", [])
            image_limit = next(
                (l for l in limits if l.get("feature_name") == "image_gen"),
                None,
            )
            if image_limit:
                print(f"Image quota remaining: {image_limit.get('remaining')}")
                print(f"Reset after: {image_limit.get('reset_after')}")
            else:
                print("No image_gen limit found in response")
            print(f"Default model: {data.get('default_model_slug')}")
        else:
            print(f"Response body: {response.text[:500]}")
            pytest.fail(f"/backend-api/conversation/init returned {response.status_code}")


class TestServiceE2E:
    """Test the full service flow with real upstream."""

    def test_import_and_generate(self) -> None:
        """End-to-end: import account and generate image."""
        pytest.skip("upstream/chatgpt.py generate_image not yet implemented")
