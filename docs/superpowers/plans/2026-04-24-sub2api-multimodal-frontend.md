# Sub2API Multimodal Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Sub2API-callable source and redesign `/ui` as a multimodal, multi-window invocation workspace.

**Architecture:** Keep changes client-side. `frontend/app.js` owns source selection, Sub2API request construction, local gateway polling, window state, and result rendering. `frontend/index.html` owns the visual system.

**Tech Stack:** React 18 UMD, browser `fetch`, `localStorage`, pytest static checks.

---

### Task 1: Frontend Static Tests

**Files:**
- Create: `tests/test_frontend_static.py`
- Read: `frontend/app.js`
- Read: `frontend/index.html`

- [x] Write tests that assert the new UI contains source selection, Sub2API URL/token inputs, multimodal tabs, window controls, `/v1/images/generations` Sub2API endpoint construction, and no hardcoded provided secret.
- [x] Run `pytest tests/test_frontend_static.py -q` and confirm it fails before implementation because the strings are absent.

### Task 2: Multimodal Workbench UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`

- [x] Replace the centered generator layout with a three-column workbench: windows sidebar, transcript main area, and right control panel.
- [x] Add modality tabs for image, video, and audio; keep video/audio disabled with planned labels.
- [x] Add source controls for Local Gateway and Sub2API, including base URL, token, remember-token checkbox, model, count, and prompt.

### Task 3: Sub2API Image Generation

**Files:**
- Modify: `frontend/app.js`

- [x] For Local Gateway, preserve the current queued `/v1/images/generations` flow and polling.
- [x] For Sub2API, call `${baseUrl}/v1/images/generations` with bearer auth and normalize `b64_json` or `url` results into the selected window transcript.
- [x] Validate prompt, URL, and token before calling Sub2API.

### Task 4: Verification

**Files:**
- Run: `tests/test_frontend_static.py`
- Run: existing pytest suite as feasible.

- [x] Run `pytest tests/test_frontend_static.py -q`.
- [x] Run `pytest tests/test_core.py -q`.
- [x] Inspect `git diff -- frontend/index.html frontend/app.js tests/test_frontend_static.py docs/superpowers`.
