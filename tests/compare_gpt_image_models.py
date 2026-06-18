#!/usr/bin/env python3
"""Manual comparison test for gpt-image-1 vs gpt-image-2.

Usage:
    python tests/compare_gpt_image_models.py

This script:
1. Uses the credentials from `.env`
2. Generates one image with `gpt-image-1`
3. Generates one image with `gpt-image-2`
4. Saves both PNGs into `/tmp`

The easiest way to judge image quality differences is to open the two files
side by side and compare them manually.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.models import AccountRecord, BrowserProfile
from upstream.chatgpt import ChatgptUpstreamClient

PROMPT = "一只戴墨镜的橘猫坐在木桌前，电影感，高清"
OUTPUT_DIR = Path("/tmp/gpt2api_model_compare")


def build_account() -> AccountRecord:
    if not settings.openai_access_token:
        raise RuntimeError("OPENAI_ACCESS_TOKEN is not configured")
    return AccountRecord(
        name="compare-models",
        access_token=settings.openai_access_token,
        browser_profile_json=BrowserProfile(
            session_token=settings.openai_session_token,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            impersonate_browser="edge",
        ).model_dump_json(),
    )


async def generate_one(model: str) -> dict[str, str | int]:
    client = ChatgptUpstreamClient(
        base_url=settings.chatgpt_base_url,
        proxy_url=settings.upstream_proxy,
    )
    result = await client.generate_image(build_account(), PROMPT, model)
    if not result.data:
        raise RuntimeError(f"{model} returned no images")

    image_bytes = base64.b64decode(result.data[0].b64_json)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{model}.png"
    output_path.write_bytes(image_bytes)

    return {
        "model": model,
        "resolved_model": result.resolved_model,
        "output_path": str(output_path),
        "size_bytes": len(image_bytes),
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
    }


async def main() -> None:
    print(f"Prompt: {PROMPT}")
    print(f"Output dir: {OUTPUT_DIR}")
    print()

    for model in ("gpt-image-1", "gpt-image-2"):
        try:
            info = await generate_one(model)
            print(f"[{model}] OK")
            print(f"  resolved_model: {info['resolved_model']}")
            print(f"  output_path:    {info['output_path']}")
            print(f"  size_bytes:     {info['size_bytes']}")
            print(f"  sha256:         {info['sha256']}")
        except Exception as exc:
            print(f"[{model}] ERROR: {exc}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
