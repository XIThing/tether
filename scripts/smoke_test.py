#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse


def build_headers(token: str, is_json: bool = True) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if is_json:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def request_json(
    base: str,
    method: str,
    path: str,
    token: str,
    payload: Optional[dict] = None,
) -> Dict[str, Any]:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80)
    body = None
    headers = build_headers(token, is_json=True)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    if resp.status < 200 or resp.status >= 300:
        raise RuntimeError(f"{method} {path} failed: {resp.status} {data}")
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {method} {path}: {exc}")


def read_sse_until_output(base: str, session_id: str, token: str, timeout_s: int) -> None:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout_s)
    headers = build_headers(token, is_json=False)
    conn.request("GET", f"/events/sessions/{session_id}", headers=headers)
    resp = conn.getresponse()
    if resp.status != 200:
        data = resp.read().decode("utf-8")
        conn.close()
        raise RuntimeError(f"SSE connect failed: {resp.status} {data}")

    start = time.monotonic()
    buffer = ""
    try:
        while time.monotonic() - start < timeout_s:
            line = resp.readline().decode("utf-8")
            if not line:
                time.sleep(0.1)
                continue
            if line == "\n":
                if buffer.startswith("data: "):
                    payload = buffer[len("data: ") :].strip()
                    buffer = ""
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "output":
                        return
                else:
                    buffer = ""
            else:
                buffer += line
        raise RuntimeError("Timed out waiting for SSE output event")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for tether agent")
    parser.add_argument("--base-url", default="http://localhost:8787")
    parser.add_argument("--token", default="")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token

    try:
        request_json(base, "GET", "/health", token)
        session = request_json(base, "POST", "/api/sessions", token, {"repo_id": "repo_smoke"})
        session_id = session.get("session", {}).get("id")
        if not session_id:
            raise RuntimeError("Missing session id in create response")
        request_json(base, "POST", f"/api/sessions/{session_id}/start", token, {"prompt": "smoke"})
        read_sse_until_output(base, session_id, token, args.timeout)
        request_json(base, "GET", f"/api/sessions/{session_id}/diff", token)
        request_json(base, "POST", f"/api/sessions/{session_id}/stop", token)
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1

    print("Smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
