#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import time
import uuid
from typing import Optional
from urllib.parse import urlparse


def request_json(base: str, method: str, path: str, payload: Optional[dict] = None) -> dict:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80)
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    if resp.status < 200 or resp.status >= 300:
        raise RuntimeError(f"{method} {path} failed: {resp.status} {data}")
    return json.loads(data) if data else {}


def sse_read_output(base: str, session_id: str, timeout_s: int, require_text: Optional[str] = None) -> str:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout_s)
    conn.request("GET", f"/events/{session_id}")
    resp = conn.getresponse()
    if resp.status != 200:
        data = resp.read().decode("utf-8")
        conn.close()
        raise RuntimeError(f"SSE connect failed: {resp.status} {data}")

    start = time.monotonic()
    try:
        while time.monotonic() - start < timeout_s:
            line = resp.fp.readline().decode("utf-8", errors="replace")
            if not line:
                time.sleep(0.05)
                continue
            if line.startswith("data: "):
                payload = line[len("data: ") :].strip()
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "output":
                    text = event.get("data", {}).get("text", "")
                    if not text.strip():
                        continue
                    if require_text and require_text.lower() not in text.lower():
                        continue
                    return text
        raise RuntimeError("Timed out waiting for SSE output")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex sidecar smoke test")
    parser.add_argument("--base-url", default="http://localhost:8788")
    parser.add_argument("--prompt", default="Remember 888.")
    parser.add_argument("--followup", default="What do you remember?")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    session_id = f"sess_{uuid.uuid4().hex[:12]}"

    request_json(
        base,
        "POST",
        "/sessions/start",
        {"session_id": session_id, "prompt": args.prompt, "approval_choice": 1},
    )

    first = sse_read_output(base, session_id, args.timeout, require_text="888")
    print("First output:")
    print(first)

    request_json(
        base,
        "POST",
        "/sessions/input",
        {"session_id": session_id, "text": args.followup},
    )

    second = sse_read_output(base, session_id, args.timeout, require_text="888")
    if not second.strip():
        raise RuntimeError("Second output was empty")
    print("Second output:")
    print(second)

    request_json(base, "POST", "/sessions/stop", {"session_id": session_id})
    print("Sidecar smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
