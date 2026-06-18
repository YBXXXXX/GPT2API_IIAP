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


class TestImageGenerationEndpoint:
    """/v1/images/generations must behave like the official synchronous endpoint."""

    def test_generation_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/v1/images/generations",
            json={"prompt": "hello", "model": "gpt-image-1", "n": 1},
        )
        assert response.status_code == 401

    def test_generation_returns_image_json(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        import base64
        import time as _time
        from app.models import ChatgptImageResult, GeneratedImageItem

        fake_result = ChatgptImageResult(
            created=int(_time.time()),
            data=[GeneratedImageItem(b64_json=base64.b64encode(b"fake-image").decode(), revised_prompt="hello")],
            resolved_model="gpt-image-1",
        )

        async def fake_generate_images_for_key(key, prompt, model, n):
            assert prompt == "hello"
            assert model == "gpt-image-1"
            assert n == 1
            return fake_result

        from app.main import app as _app
        monkeypatch.setattr(_app.state.service, "generate_images_for_key", fake_generate_images_for_key)

        response = client.post(
            "/v1/images/generations",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"prompt": "hello", "model": "gpt-image-1", "n": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert "request_id" not in data
        assert "created" in data
        assert data["data"][0]["b64_json"] == base64.b64encode(b"fake-image").decode()

    def test_queue_generation_keeps_async_contract(self, client: TestClient) -> None:
        response = client.post(
            "/v1/queue/generations",
            json={"prompt": "hello", "model": "gpt-image-1", "n": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "request_id" in data


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

    def test_edit_with_image_delegates_to_upstream(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        import base64
        from app.models import ChatgptImageResult, GeneratedImageItem
        import time as _time

        fake_result = ChatgptImageResult(
            created=int(_time.time()),
            data=[GeneratedImageItem(b64_json=base64.b64encode(b"fake-image").decode(), revised_prompt="hello")],
            resolved_model="gpt-image-1",
        )

        async def fake_edit_image(account, prompt, model, image_data, file_name, mime_type):
            assert image_data == b"fake-image-bytes"
            assert file_name == "cat.png"
            assert mime_type == "image/png"
            return fake_result

        from app.main import app as _app
        monkeypatch.setattr(_app.state.service.upstream, "edit_image", fake_edit_image)

        response = client.post(
            "/v1/images/edits",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            data={"prompt": "hello", "model": "gpt-image-1", "n": "1"},
            files={"image": ("cat.png", b"fake-image-bytes", "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert "b64_json" in data["data"][0]


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
        assert any(item["access_token"] == "test-token-123" for item in data["items"])

    def test_import_session_json(self, client: TestClient) -> None:
        session_json = {
            "user": {
                "id": "user-demo",
                "email": "demo@example.com",
            },
            "account": {
                "planType": "plus",
            },
            "accessToken": "session-access-token-123",
            "sessionToken": "session-cookie-456",
        }
        response = client.post(
            "/admin/accounts/import",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={"session_jsons": [__import__("json").dumps(session_json)]},
        )
        assert response.status_code == 200
        data = response.json()
        item = next(i for i in data["items"] if i["access_token"] == "session-access-token-123")
        assert item["email"] == "demo@example.com"
        assert item["plan_type"] == "plus"

    def test_import_empty(self, client: TestClient) -> None:
        response = client.post(
            "/admin/accounts/import",
            headers={"authorization": f"Bearer {settings.admin_token}"},
            json={},
        )
        assert response.status_code == 400


class TestAccountSchedulerBackoff:
    """Transient account failures should temporarily remove bad accounts from routing."""

    def test_timeout_failure_puts_account_into_backoff(self, tmp_path) -> None:
        from app.models import AccountRecord
        from app.service import AppService
        from storage.control import ControlDb

        class DummyUpstream:
            pass

        db = ControlDb(tmp_path / "control.db")
        service = AppService(storage=db, admin_token="change-me", upstream=DummyUpstream())
        bad = AccountRecord(name="bad", access_token="bad-token", status="active", quota_remaining=10, quota_known=True)
        good = AccountRecord(name="good", access_token="good-token", status="active", quota_remaining=5, quota_known=True)
        db.upsert_account(bad)
        db.upsert_account(good)

        service._record_account_failure(bad, "operation timed out while connecting upstream")

        selected = service.select_best_account()
        assert selected is not None
        assert selected.name == "good"

    def test_prompt_refusal_does_not_put_account_into_backoff(self, tmp_path) -> None:
        from app.models import AccountRecord
        from app.service import AppService
        from storage.control import ControlDb

        class DummyUpstream:
            pass

        db = ControlDb(tmp_path / "control.db")
        service = AppService(storage=db, admin_token="change-me", upstream=DummyUpstream())
        only = AccountRecord(name="only", access_token="only-token", status="active", quota_remaining=10, quota_known=True)
        db.upsert_account(only)

        service._record_account_failure(only, "no file IDs found after polling")

        selected = service.select_best_account()
        assert selected is not None
        assert selected.name == "only"


class TestQueuePartialSuccess:
    """One failed image in a batch should not discard successful images."""

    def test_batch_generates_images_serially_within_one_job(self, tmp_path) -> None:
        import asyncio

        from app.models import AccountRecord, ChatgptImageResult, GeneratedImageItem
        from app.queue_manager import GenerationJob, QueueManager
        from storage.control import ControlDb

        class DummyLease:
            def release(self) -> None:
                return None

        class DummyUpstream:
            def __init__(self) -> None:
                self.active = 0
                self.max_active = 0

            async def generate_image(self, account, prompt, model):
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                await asyncio.sleep(0.01)
                self.active -= 1
                return ChatgptImageResult(
                    created=1,
                    data=[GeneratedImageItem(b64_json="ZmFrZQ==", revised_prompt=prompt)],
                    resolved_model=model,
                )

        class DummyService:
            def __init__(self, storage, upstream):
                self.storage = storage
                self.upstream = upstream

            async def acquire_best_account_for_queue(self):
                return self.storage.list_accounts()[0], DummyLease()

            async def _refresh_account_if_needed(self, account):
                return account

            def _record_account_success(self, account):
                return None

            def _record_account_failure(self, account, error_message):
                return None

        async def run_test():
            db = ControlDb(tmp_path / "control.db")
            upstream = DummyUpstream()
            db.upsert_account(
                AccountRecord(
                    name="demo",
                    access_token="token",
                    status="active",
                    quota_remaining=10,
                    quota_known=True,
                )
            )
            queue = QueueManager(DummyService(db, upstream), workers=1)
            result = await queue._execute_job(GenerationJob(prompt="hello", model="gpt-image-2", n=2))
            assert len(result["data"]) == 2
            assert upstream.max_active == 1

        asyncio.run(run_test())

    def test_worker_classifies_prompt_refusal_error(self, tmp_path) -> None:
        import asyncio

        from app.models import AccountRecord
        from app.queue_manager import GenerationJob, QueueManager
        from storage.control import ControlDb

        refusal = "非常抱歉，生成的图片可能违反了关于轻度性暗示或挑逗性主题的防护限制。"

        class DummyLease:
            def release(self) -> None:
                return None

        class DummyUpstream:
            async def generate_image(self, account, prompt, model):
                raise RuntimeError(refusal)

        class DummyService:
            def __init__(self, storage):
                self.storage = storage
                self.upstream = DummyUpstream()

            async def acquire_best_account_for_queue(self):
                return self.storage.list_accounts()[0], DummyLease()

            async def _refresh_account_if_needed(self, account):
                return account

            def _record_account_success(self, account):
                return None

            def _record_account_failure(self, account, error_message):
                return None

        async def run_test():
            db = ControlDb(tmp_path / "control.db")
            db.upsert_account(
                AccountRecord(
                    name="demo",
                    access_token="token",
                    status="active",
                    quota_remaining=10,
                    quota_known=True,
                )
            )
            queue = QueueManager(DummyService(db), workers=1)
            await queue.submit(GenerationJob(prompt="hello", model="gpt-image-2", n=1, request_id="req-refusal"))
            worker = asyncio.create_task(queue._worker_loop())
            await asyncio.wait_for(queue._queue.join(), timeout=1)
            worker.cancel()
            result = queue.get_result("req-refusal")
            assert result is not None
            assert result["status"] == "error"
            assert result["error_type"] == "prompt_rejection"
            assert result["upstream_message"] == refusal

        asyncio.run(run_test())

    def test_batch_returns_partial_success_when_one_image_fails(self, tmp_path) -> None:
        import asyncio

        from app.models import AccountRecord, ChatgptImageResult, GeneratedImageItem
        from app.queue_manager import GenerationJob, QueueManager
        from storage.control import ControlDb

        class DummyLease:
            def release(self) -> None:
                return None

        class DummyUpstream:
            def __init__(self) -> None:
                self.calls = 0
                self.lock = asyncio.Lock()

            async def generate_image(self, account, prompt, model):
                async with self.lock:
                    self.calls += 1
                    call_no = self.calls
                await asyncio.sleep(0.01)
                if call_no == 1:
                    raise RuntimeError("synthetic single-image failure")
                return ChatgptImageResult(
                    created=1,
                    data=[GeneratedImageItem(b64_json="ZmFrZQ==", revised_prompt=prompt)],
                    resolved_model=model,
                )

        class DummyService:
            def __init__(self, storage, upstream):
                self.storage = storage
                self.upstream = upstream

            async def acquire_best_account_for_queue(self):
                return self.storage.list_accounts()[0], DummyLease()

            async def _refresh_account_if_needed(self, account):
                return account

            def _record_account_success(self, account):
                return None

            def _record_account_failure(self, account, error_message):
                return None

        async def run_test():
            db = ControlDb(tmp_path / "control.db")
            db.upsert_account(
                AccountRecord(
                    name="demo",
                    access_token="token",
                    status="active",
                    quota_remaining=10,
                    quota_known=True,
                )
            )
            service = DummyService(db, DummyUpstream())
            queue = QueueManager(service, workers=1)
            result = await queue._execute_job(GenerationJob(prompt="hello", model="gpt-image-2", n=2))
            assert len(result["data"]) == 1
            assert result["partial_error"] == "synthetic single-image failure"

        asyncio.run(run_test())
