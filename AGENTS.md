# Repository Guidelines

## Project Structure & Module Organization

This repository is a FastAPI gateway for ChatGPT Web image generation with a small static React frontend.

- `app/` contains `main.py`, public/admin routes, schemas, queue manager, service layer, and settings.
- `accounts/`, `scheduler/`, `storage/`, and `upstream/` hold account import, routing/throttling, SQLite persistence, and ChatGPT Web protocol code.
- `frontend/` contains static pages and browser scripts for `/ui` and `/panel`.
- `tests/` contains pytest coverage for API behavior, scheduling, keys, and integration helpers.
- `tools/frp/` contains bundled FRP binaries/configuration; avoid modifying these unless updating tunneling support.

## Build, Test, and Development Commands

- `python3 -m venv venv && source venv/bin/activate` creates a local virtual environment.
- `pip install -r requirements.txt` installs FastAPI, pytest, httpx, and runtime dependencies.
- `./start.sh` creates `venv` if needed, installs dependencies, reads `.env`, and starts the server with logs at `logs/server.log`.
- `python -m app.main` runs the FastAPI app directly for local development.
- `pytest` runs the test suite. Use `pytest tests/test_core.py -q` for a focused core check.
- `curl http://127.0.0.1:8787/healthz` verifies a running local service.

## Coding Style & Naming Conventions

Use Python 3.11+ with 4-space indentation, type hints for public functions, and Pydantic models for structured data. Keep route handlers thin and place business behavior in service, scheduler, storage, or upstream modules. Use `snake_case` for Python files, functions, variables, and test names; use `PascalCase` for classes. Frontend files are plain JavaScript/HTML; keep changes dependency-free and consistent with existing browser-side React code.

## Testing Guidelines

Tests use `pytest`, `pytest-asyncio`, and FastAPI `TestClient`. Name files `test_*.py`, classes `TestFeatureName`, and methods `test_expected_behavior`. Add tests for route validation, auth, scheduler changes, storage migrations, and upstream error mapping. Avoid tests that require real ChatGPT credentials unless explicitly isolated.

## Commit & Pull Request Guidelines

The current history only shows an initial commit, so use clear imperative subjects such as `Add key lifecycle validation` or `Fix queue status response`. Pull requests should include a summary, test results, configuration changes, and screenshots when touching `frontend/`. Link related issues and call out any `.env`, database, or migration impact.

## Security & Configuration Tips

Keep `.env` local and never commit real `ADMIN_TOKEN`, access tokens, session tokens, API keys, or SQLite databases. Treat `data/`, `logs/`, and `.pid` as runtime artifacts. When changing auth or account import behavior, verify both public API and `/admin/*` paths.
