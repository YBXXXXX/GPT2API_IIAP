# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

GPT2API_IIAP is a FastAPI gateway that exposes ChatGPT Web image generation through OpenAI-compatible endpoints, plus a static browser React UI and admin panel. The service supports imported ChatGPT Web accounts, API keys, per-account scheduling, a global FIFO generation queue, and SQLite persistence.

## Common commands

```bash
# Create and activate a local virtual environment
python3 -m venv venv && source venv/bin/activate

# Install runtime and test dependencies
pip install -r requirements.txt

# Run the full test suite
pytest

# Run a focused test file or single test
pytest tests/test_core.py -q
pytest tests/test_core.py::TestPublicAuth::test_models_no_auth_required -q

# Run frontend static architecture checks
pytest tests/test_frontend_static.py -q

# Run the app directly in the foreground
python -m app.main

# Start via the repository script; this creates venv if needed, installs deps, reads .env, and logs to logs/server.log
./start.sh

# Check a local running service
curl http://127.0.0.1:8787/healthz
```

There is no configured package build step and no project lint config in this repository. The frontend is loaded directly in the browser from `frontend/index.html` and `frontend/admin.html` using React/Babel CDN scripts.

## Runtime configuration

Settings are loaded by `app/config.py` from environment variables and `.env`. Important variables include `HOST`, `PORT`, `STORAGE_DIR`, `ADMIN_TOKEN`, `CHATGPT_BASE_URL`, `UPSTREAM_PROXY`, `OPENAI_ACCESS_TOKEN`, and `OPENAI_SESSION_TOKEN`. Local state is written under `data/`, runtime logs under `logs/`, and the start script writes `.pid`.

## High-level architecture

- `app/main.py` constructs the FastAPI app, mounts public/admin routers, serves static frontend files at `/ui` and `/panel`, initializes `ControlDb`, `ChatgptUpstreamClient`, `AppService`, and starts an 8-worker `QueueManager` during lifespan startup.
- `app/api_public.py` implements OpenAI-compatible public endpoints. `/v1/images/generations` submits anonymous or optionally authenticated jobs to the global queue and returns a `request_id`; `/v1/queue/result/{id}` is used by the UI to poll queued/processing/done/error states. `/v1/images/edits`, chat completions, and responses are present but not fully implemented.
- `app/api_admin.py` contains bearer-token-protected admin routes for status, account import/refresh/delete/update, API key lifecycle, and usage listing. Admin auth compares the bearer token against `settings.admin_token` through `AppService`.
- `app/service.py` is the orchestration layer. It owns public key auth/quota checks, default API key creation from `ADMIN_TOKEN`, account import/update/refresh, API key lifecycle, account selection, per-key/per-account scheduler leases, account failure/backoff handling, and usage settlement.
- `app/queue_manager.py` is an in-memory FIFO queue with async workers. Each queued generation job generates requested images serially, updates partial progress in `_results`, retries across routeable accounts for transient/account failures, and classifies errors such as prompt rejections or invalid tokens.
- `scheduler/local_scheduler.py` enforces in-memory concurrency and start-interval limits using leases. `scheduler/routing.py` selects accounts; `AUTO` prefers known quota, then higher remaining quota, then least recently used, while `FIXED` keeps candidate order.
- `storage/control.py` wraps SQLite access and `storage/migrations.py` bootstraps control-plane tables for accounts, API keys, runtime config, event outbox, and usage events. Tests often create isolated `ControlDb(tmp_path / "control.db")` instances.
- `accounts/importer.py` normalizes raw access tokens and ChatGPT session JSON into `AccountRecord` objects with browser profile hints.
- `upstream/chatgpt.py` uses `curl_cffi` browser impersonation to call ChatGPT Web endpoints. The image flow bootstraps the web session, requests chat requirements, computes sentinel PoW when required, posts a conversation, polls for image file IDs, downloads image bytes, and returns base64 image payloads.
- `frontend/` contains two browser-only React surfaces: the multimodal user console under `/ui` and the admin panel under `/panel`. The user console is modularized under `frontend/src/`; components should stay presentation-focused while API clients, storage, image normalization, and workspace state live in their respective `src/api`, `src/utils`, and `src/state` modules.

## Testing notes

- Core tests in `tests/test_core.py` use FastAPI `TestClient`, temporary SQLite databases, and dummy upstream/service objects to avoid real ChatGPT credentials.
- `tests/test_frontend_static.py` asserts the browser-only frontend module layout and guards against transport/storage logic moving into components or hardcoded secrets.
- `tests/test_e2e.py` contains real ChatGPT Web checks that depend on `.env` credentials and upstream connectivity; some tests are explicitly skipped. Avoid relying on real upstream credentials for normal unit coverage.

## Repository-specific guidance

- Keep HTTP handlers thin; put business behavior in `AppService`, scheduling modules, storage, or upstream code.
- When changing auth, quota, account routing, or import behavior, verify both public endpoints and `/admin/*` paths.
- Treat `data/`, `logs/`, `.pid`, and bundled `tools/frp/` artifacts as runtime/support files; avoid modifying bundled FRP files unless the task is specifically about tunneling support.
- The README notes that stored `refresh_token` values are not automatically refreshed because OpenAI OAuth refresh reuse can invalidate other sessions; preserve that behavior unless the task explicitly changes token refresh semantics.
