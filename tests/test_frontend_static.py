#!/usr/bin/env python3
"""Static checks for the browser-only multimodal frontend."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend() -> str:
    parts = []
    for path in sorted((ROOT / "frontend").rglob("*")):
        if path.suffix in {".html", ".js", ".css"}:
            parts.append(path.read_text())
    return "\n".join(parts)


def frontend_path(relative: str) -> Path:
    return ROOT / "frontend" / relative


def test_frontend_exposes_sub2api_source_controls() -> None:
    source = read_frontend()

    assert "Local Gateway" in source
    assert "Sub2API" in source
    assert "sub2apiBaseUrl" in source
    assert "sub2apiToken" in source
    assert "Remember token" in source


def test_frontend_has_multimodal_and_multi_window_affordances() -> None:
    source = read_frontend()

    assert "modalityTabs" in source
    assert "Image" in source
    assert "Video" in source
    assert "Audio" in source
    assert "conversationWindows" in source
    assert "addWindow" in source
    assert "deleteWindow" in source


def test_frontend_uses_modular_no_build_structure() -> None:
    expected_paths = [
        "src/api/localGatewayClient.js",
        "src/api/sub2apiClient.js",
        "src/api/imageResponse.js",
        "src/utils/ids.js",
        "src/utils/storage.js",
        "src/utils/images.js",
        "src/state/workspaceState.js",
        "src/components/WindowSidebar.js",
        "src/components/MessageList.js",
        "src/components/ComposerPanel.js",
        "src/components/SourceSettings.js",
        "src/components/ModalityTabs.js",
        "src/App.js",
    ]

    for relative in expected_paths:
        assert frontend_path(relative).exists(), relative

    index = frontend_path("index.html").read_text()
    assert 'src="workbench.js"' not in index
    for relative in expected_paths:
        assert f'src="{relative}"' in index


def test_frontend_components_do_not_own_transport_or_storage() -> None:
    for path in frontend_path("src/components").glob("*.js"):
        text = path.read_text()
        assert "fetch(" not in text, path
        assert "localStorage" not in text, path


def test_frontend_builds_direct_sub2api_image_request() -> None:
    source = read_frontend()

    assert "/v1/images/generations" in source
    assert "Authorization" in source
    assert "Bearer ${token}" in source
    assert "normalizeImageResponse" in source


def test_frontend_does_not_persist_image_payloads_to_local_storage() -> None:
    source = read_frontend()

    assert "serializeWindowsForStorage" in source
    assert "safeSetLocalStorage" in source
    assert "JSON.stringify(serializeWindowsForStorage(conversationWindows))" in source
    assert "JSON.stringify(conversationWindows)" not in source
    assert "src: ''" in source
    assert "b64_json: ''" in source


def test_frontend_does_not_hardcode_runtime_secrets() -> None:
    source = read_frontend()

    assert "ANTHROPIC_AUTH_TOKEN" not in source
    assert "ANTHROPIC_BASE_URL" not in source
    assert "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC" not in source
    assert re.search(r"sk-[a-f0-9]{32,}", source) is None
