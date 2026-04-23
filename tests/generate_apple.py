#!/usr/bin/env python3
"""Direct test: generate an apple image via ChatGPT Web protocol."""

import base64
import hashlib
import json
import random
import time
import uuid

from curl_cffi import requests as curl_requests

from app.config import settings


def hex_decode(raw: str) -> bytes:
    """Decode hex string to bytes."""
    return bytes(int(raw[i:i+2], 16) for i in range(0, len(raw), 2))


def build_pow_config(user_agent: str, scripts: list[str], build_id: str | None) -> list:
    """Build the PoW config array (migrated from Rust)."""
    # Simplified: use fixed values for random picks
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
    
    # Pick a script URL containing sentinel/sdk.js
    sdk_script = ""
    for s in scripts:
        if "sentinel/sdk.js" in s:
            sdk_script = s
            break
    if not sdk_script:
        sdk_script = "https://chatgpt.com/backend-api/sentinel/sdk.js"
    
    ts_ms = now * 1000.0
    
    return [
        3000,
        time.strftime("%a %b %d %Y %H:%M:%S GMT-0500 (Eastern Standard Time)", time.gmtime(now + 5*3600)),
        4294705152,
        0,
        user_agent,
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


def generate_proof_token(seed: str, difficulty: str, config: list) -> str:
    """Generate proof-of-work token (migrated from Rust)."""
    part1_json = json.dumps(config[:3], separators=(',', ':'))
    part1 = part1_json.rstrip(']') + ","
    
    part2_json = json.dumps(config[4:9], separators=(',', ':'))
    part2 = "," + part2_json[1:-1] + ","
    
    part3_json = json.dumps(config[10:], separators=(',', ':'))
    part3 = "," + part3_json[1:]
    
    target = hex_decode(difficulty)
    
    for i in range(500_000):
        attempt = (
            part1.encode()
            + str(i).encode()
            + part2.encode()
            + str(i >> 1).encode()
            + part3.encode()
        )
        encoded = base64.b64encode(attempt).decode()
        
        # SHA3-512 of seed + encoded
        hasher = hashlib.sha3_512()
        hasher.update(seed.encode())
        hasher.update(encoded.encode())
        digest = hasher.digest()
        
        if digest[:len(target)] <= target:
            return f"gAAAAAB{encoded}"
    
    # Fallback
    fallback = base64.b64encode(f'"{seed}"'.encode()).decode()
    return f"wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D{fallback}"


def main():
    token = settings.openai_access_token
    session = settings.openai_session_token
    proxy = settings.upstream_proxy
    base = "https://chatgpt.com"
    
    session_req = curl_requests.Session(impersonate="edge")
    if proxy:
        session_req.proxies = {"http": proxy, "https": proxy}
    
    headers = {
        "authorization": f"Bearer {token}",
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "origin": base,
        "referer": f"{base}/",
    }
    if session:
        headers["cookie"] = f"__Secure-next-auth.session-token={session}"
    
    # Step 1: bootstrap
    print("[1] Bootstrap homepage...")
    resp = session_req.get(base, headers=headers, timeout=30)
    print(f"Status: {resp.status_code}")
    
    # Extract scripts and build_id from HTML
    scripts = []
    build_id = None
    for line in resp.text.split("\n"):
        if '<script' in line and 'src=' in line:
            # crude extraction
            start = line.find('src="')
            if start != -1:
                end = line.find('"', start + 5)
                if end != -1:
                    scripts.append(line[start+5:end])
        if '"buildId"' in line:
            try:
                data = json.loads(line[line.find('{'):line.rfind('}')+1])
                build_id = data.get("buildId")
            except:
                pass
    
    device_id = str(uuid.uuid4())
    print(f"Device ID: {device_id}")
    print(f"Scripts found: {len(scripts)}")
    print(f"Build ID: {build_id}")
    
    # Step 2: chat requirements
    print("\n[2] Chat requirements...")
    req_headers = {
        **headers,
        "content-type": "application/json",
        "oai-device-id": device_id,
    }
    
    resp_req = session_req.post(
        f"{base}/backend-api/sentinel/chat-requirements",
        headers=req_headers,
        json={"conversation_mode_kind": "primary_assistant"},
        timeout=30,
    )
    print(f"Status: {resp_req.status_code}")
    req_data = resp_req.json()
    print(f"Response: {json.dumps(req_data, indent=2)[:800]}")
    
    chat_token = req_data.get("token", "")
    pow_info = req_data.get("proofofwork", {})
    pow_required = pow_info.get("required", False)
    
    # Step 3: Generate PoW if needed
    proof_token = None
    if pow_required:
        seed = pow_info.get("seed", "")
        difficulty = pow_info.get("difficulty", "")
        print(f"\n[3] Generating PoW token (seed={seed[:20]}..., difficulty={difficulty})...")
        
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        config = build_pow_config(ua, scripts, build_id)
        proof_token = generate_proof_token(seed, difficulty, config)
        print(f"Proof token: {proof_token[:60]}...")
    
    # Step 4: Send conversation
    print("\n[4] Send conversation (生成一个苹果)...")
    message_id = str(uuid.uuid4())
    parent_id = str(uuid.uuid4())
    
    # Build client contextual info
    seed = random.randint(1, 100000)
    contextual_info = {
        "is_dark_mode": False,
        "time_since_loaded": 50 + (seed % 450),
        "page_height": 500 + (seed % 500),
        "page_width": 1000 + (seed % 1000),
        "pixel_ratio": 1.2,
        "screen_height": 800 + (seed % 400),
        "screen_width": 1200 + (seed % 1000),
    }
    
    payload = {
        "action": "next",
        "messages": [
            {
                "id": message_id,
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["生成一个苹果"]},
                "metadata": {"attachments": []},
            }
        ],
        "parent_message_id": parent_id,
        "model": "gpt-image-1",
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
        **req_headers,
        "accept": "text/event-stream",
        "content-type": "application/json",
        "oai-language": "zh-CN",
        "oai-client-build-number": "5955942",
        "oai-client-version": "prod-be885abbfcfe7b1f511e88b3003d9ee44757fbad",
        "openai-sentinel-chat-requirements-token": chat_token,
    }
    if proof_token:
        conv_headers["openai-sentinel-proof-token"] = proof_token
    
    # Use HTTP/1.1 to avoid HTTP/2 stream issues with SSE
    print("\n[5] Parse SSE response...")
    try:
        resp_conv = session_req.post(
            f"{base}/backend-api/conversation",
            headers=conv_headers,
            json=payload,
            timeout=120,
        )
    except Exception as e:
        print(f"Request error (will retry without body read): {e}")
        # Fallback: use stream but catch errors
        import urllib.request
        req = urllib.request.Request(
            f"{base}/backend-api/conversation",
            data=json.dumps(payload).encode(),
            headers=conv_headers,
            method="POST",
        )
        resp_conv = urllib.request.urlopen(req, timeout=120)
        resp_text = resp_conv.read().decode()
    else:
        print(f"Status: {resp_conv.status_code}")
        print(f"Content-Type: {resp_conv.headers.get('content-type', 'unknown')}")
        if resp_conv.status_code != 200:
            print(f"Error: {resp_conv.text[:500]}")
            return
        resp_text = resp_conv.text
    
    file_ids = []
    assistant_text = ""
    conv_id = ""
    
    for line in resp_text.split("\n"):
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
            
            msg = event.get("message", {})
            if msg:
                content = msg.get("content", {})
                parts = content.get("parts", [])
                for part in parts:
                    if isinstance(part, str):
                        assistant_text += part
                
                # Check metadata for image tool calls
                metadata = msg.get("metadata", {})
                if "file_ids" in metadata:
                    file_ids.extend(metadata["file_ids"])
                    
                # Check for inline file references in text
                import re
                refs = re.findall(r'file-service://([a-zA-Z0-9_-]+)', assistant_text)
                file_ids.extend(refs)
                    
        except json.JSONDecodeError:
            continue
    
    print(f"Conversation ID: {conv_id}")
    print(f"Text: {assistant_text[:300]}")
    print(f"File IDs from SSE: {file_ids}")
    
    # Step 6: Poll for image IDs if not found in SSE
    if not file_ids and conv_id:
        print("\n[6] Polling conversation for image IDs...")
        deadline = time.time() + 45
        while time.time() < deadline:
            poll_resp = session_req.get(
                f"{base}/backend-api/conversation/{conv_id}",
                headers=req_headers,
                timeout=30,
            )
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                mapping = poll_data.get("mapping", {})
                for node in mapping.values():
                    msg = node.get("message", {})
                    if not msg:
                        continue
                    if msg.get("author", {}).get("role") != "tool":
                        continue
                    if msg.get("metadata", {}).get("async_task_type") != "image_gen":
                        continue
                    if msg.get("content", {}).get("content_type") != "multimodal_text":
                        continue
                    parts = msg.get("content", {}).get("parts", [])
                    for part in parts:
                        pointer = part.get("asset_pointer", "")
                        if pointer.startswith("file-service://"):
                            file_ids.append(pointer[15:])
                        elif pointer.startswith("sediment://"):
                            file_ids.append(f"sed:{pointer[11:]}")
                if file_ids:
                    print(f"Found file IDs via polling: {file_ids}")
                    break
            time.sleep(3)
    
    if not file_ids:
        print("\n[!] No file IDs found after polling. The response might contain only text or a refusal.")
        return
    
    # Step 7: Download images
    print("\n[7] Download images...")
    for fid in set(file_ids):
        # Handle sediment:// prefix
        if fid.startswith("sed:"):
            raw_id = fid[4:]
            dl_url = f"{base}/backend-api/conversation/{conv_id}/attachment/{raw_id}/download"
        else:
            dl_url = f"{base}/backend-api/files/{fid}/download"
        
        dl_resp = session_req.get(dl_url, headers=req_headers, timeout=30)
        print(f"File {fid} download URL status: {dl_resp.status_code}")
        if dl_resp.status_code == 200:
            dl_data = dl_resp.json()
            url = dl_data.get("download_url", "")
            if url:
                img_resp = session_req.get(url, timeout=60)
                if img_resp.status_code == 200:
                    fname = f"/tmp/chatgpt_apple_{fid.replace(':', '_')}.png"
                    with open(fname, "wb") as f:
                        f.write(img_resp.content)
                    print(f"Saved: {fname} ({len(img_resp.content)} bytes)")
                else:
                    print(f"Failed to download image: {img_resp.status_code}")
        else:
            print(f"Failed to get download URL: {dl_resp.text[:200]}")


if __name__ == "__main__":
    main()
