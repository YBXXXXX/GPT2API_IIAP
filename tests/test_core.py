#!/usr/bin/env python3
"""Basic tests for GPT2API_IIAP core fixes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestAdminAuth:
    """Admin endpoints must return 401 when auth is missing or wrong."""

    def test_status_missing_auth(self, client: TestClient) -> None:
        response = client.get("/admin/status")
        assert response.status_code == 401

    def test_status_wrong_auth(self, client: TestClient) -> None:
        response = client.get("/admin/status", headers={"authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_status_valid_auth(self, client: TestClient) -> None:
        response = client.get("/admin/status", headers={"authorization": f"Bearer {settings.admin_token}"})
        assert response.status_code == 200
        data = response.json()
        assert "accounts_total" in data


class TestAdminUsageQuery:
    """Usage query parameter must be parsed and validated."""

    def test_usage_valid_limit(self, client: TestClient) -> None:
        response = client.get(
            "/admin/usage?limit=3",
            headers={"authorization": f"Bearer {settings.admin_token}"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_usage_invalid_limit(self, client: TestClient) -> None:
        response = client.get(
            "/admin/usage?limit=abc",
            headers={"authorization": f"Bearer {settings.admin_token}"},
        )
        assert response.status_code == 422

    def test_usage_negative_limit(self, client: TestClient) -> None:
        response = client.get(
            "/admin/usage?limit=-1",
            headers={"authorization": f"Bearer {settings.admin_token}"},
        )
        assert response.status_code == 422


class TestPublicAuth:
    """Public endpoints must authenticate bearer tokens."""

    def test_login_with_admin_token(self, client: TestClient) -> None:
        response = client.get(
            "/auth/login",
            headers={"authorization": f"Bearer {settings.admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["key"]["id"] == "default"

    def test_login_missing_auth(self, client: TestClient) -> None:
        response = client.get("/auth/login")
        assert response.status_code == 401

    def test_models_no_auth_required(self, client: TestClient) -> None:
        response = client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"


class TestImageEditMultipart:
    """/v1/images/edits must accept OpenAI-compatible multipart form data."""

    def test_edit_missing_image(self, client: TestClient) -> None:
        response = client.post(
            "/v1/images/edits",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            data={"prompt": "hello", "model": "gpt-image-1", "n": "1"},
        )
        assert response.status_code == 400
        assert "image" in response.json()["detail"].lower()

    def test_edit_with_image_upstream_not_ready(self, client: TestClient) -> None:
        response = client.post(
            "/v1/images/edits",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            data={"prompt": "hello", "model": "gpt-image-1", "n": "1"},
            files={"image": ("cat.png", b"fake-image-bytes", "image/png")},
        )
        # upstream is NotImplementedError -> mapped to 502
        assert response.status_code == 502


class TestSchedulerLease:
    """LocalRequestScheduler must release leases so slots become reusable."""

    def test_lease_release_allows_reuse(self) -> None:
        from scheduler.local_scheduler import LocalRequestScheduler

        scheduler = LocalRequestScheduler()
        lease1 = scheduler.try_acquire("k", 1, None)
        assert type(lease1).__name__ == "Lease"

        lease2 = scheduler.try_acquire("k", 1, None)
        assert type(lease2).__name__ == "Rejection"

        # explicitly release
        lease1.release()

        lease3 = scheduler.try_acquire("k", 1, None)
        assert type(lease3).__name__ == "Lease"

    def test_pacing_interval_blocks_then_allows(self) -> None:
        import time

        from scheduler.local_scheduler import LocalRequestScheduler

        scheduler = LocalRequestScheduler()
        lease1 = scheduler.try_acquire("k", None, 500)
        assert type(lease1).__name__ == "Lease"
        lease1.release()

        lease2 = scheduler.try_acquire("k", None, 500)
        assert type(lease2).__name__ == "Rejection"
        assert lease2.wait_ms > 0


class TestKeyValidation:
    """Key create/update must reject invalid input."""

    def test_create_key_empty_name(self, client: TestClient) -> None:
        response = client.post(
            "/admin/keys",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"name": "   ", "quota_total_calls": 10},
        )
        assert response.status_code == 400

    def test_create_key_negative_quota(self, client: TestClient) -> None:
        response = client.post(
            "/admin/keys",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"name": "demo", "quota_total_calls": -1},
        )
        assert response.status_code == 400

    def test_create_key_invalid_status(self, client: TestClient) -> None:
        response = client.post(
            "/admin/keys",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"name": "demo", "quota_total_calls": 10, "status": "deleted"},
        )
        assert response.status_code == 400

    def test_create_key_invalid_route_strategy(self, client: TestClient) -> None:
        response = client.post(
            "/admin/keys",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"name": "demo", "quota_total_calls": 10, "route_strategy": "random"},
        )
        assert response.status_code == 400

    def test_create_key_success(self, client: TestClient) -> None:
        response = client.post(
            "/admin/keys",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"name": "demo", "quota_total_calls": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "demo"
        assert data["quota_total_calls"] == 10
        assert data["secret_plaintext"].startswith("sk-")

    def test_key_lifecycle(self, client: TestClient) -> None:
        # create
        create = client.post(
            "/admin/keys",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"name": "lifecycle", "quota_total_calls": 7, "route_strategy": "fixed"},
        )
        assert create.status_code == 200
        created = create.json()
        key_id = created["id"]

        # list contains it
        listing = client.get("/admin/keys", headers={"authorization": f"Bearer {settings.admin_token}"})
        assert any(k["id"] == key_id for k in listing.json())

        # patch
        patch = client.patch(
            f"/admin/keys/{key_id}",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"name": "lifecycle-renamed", "status": "disabled", "quota_total_calls": 9},
        )
        assert patch.status_code == 200
        patched = patch.json()
        assert patched["name"] == "lifecycle-renamed"
        assert patched["status"] == "disabled"
        assert patched["quota_total_calls"] == 9

        # rotate
        rotate = client.post(
            f"/admin/keys/{key_id}/rotate",
            headers={"authorization": f"Bearer {settings.admin_token}"},
        )
        assert rotate.status_code == 200
        rotated = rotate.json()
        assert rotated["secret_plaintext"] != created["secret_plaintext"]

        # delete
        delete = client.delete(
            f"/admin/keys/{key_id}",
            headers={"authorization": f"Bearer {settings.admin_token}"},
        )
        assert delete.status_code == 200

        # confirm gone
        listing2 = client.get("/admin/keys", headers={"authorization": f"Bearer {settings.admin_token}"})
        assert not any(k["id"] == key_id for k in listing2.json())


class TestAccountImport:
    """Account import must create selectable accounts."""

    def test_import_token(self, client: TestClient) -> None:
        response = client.post(
            "/admin/accounts/import",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"access_tokens": ["test-token-123"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["access_token"] == "test-token-123"

    def test_import_empty(self, client: TestClient) -> None:
        response = client.post(
            "/admin/accounts/import",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={},
        )
        assert response.status_code == 400
