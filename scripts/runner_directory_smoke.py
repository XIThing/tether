#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import tempfile
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for session directory wiring")
    parser.add_argument("--base-url", default="http://localhost:8787")
    parser.add_argument("--token", default="")
    parser.add_argument("--start", action="store_true", help="Start and stop a session after create")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token or os.environ.get("AGENT_TOKEN", "")

    temp_dir = tempfile.mkdtemp(prefix="tether_smoke_dir_")
    expected = os.path.abspath(temp_dir)

    session_id = None
    try:
        request_json(base, "GET", "/api/health", token)
        created = request_json(
            base,
            "POST",
            "/api/sessions",
            token,
            {"repo_id": "repo_smoke_dir", "directory": expected},
        )
        session = created.get("session") or {}
        session_id = session.get("id")
        if not session_id:
            raise RuntimeError("Missing session id in create response")
        if session.get("directory") != expected:
            raise RuntimeError(
                f"Session directory mismatch: expected {expected}, got {session.get('directory')}"
            )
        if session.get("directory_has_git") not in (False, 0):
            raise RuntimeError("Expected directory_has_git to be false for temp dir")
        if args.start:
            request_json(
                base,
                "POST",
                f"/api/sessions/{session_id}/start",
                token,
                {"prompt": "smoke dir"},
            )
            request_json(base, "POST", f"/api/sessions/{session_id}/stop", token)
    except Exception as exc:
        print(f"Directory smoke test failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if session_id:
            try:
                request_json(base, "DELETE", f"/api/sessions/{session_id}", token)
            except Exception:
                pass

    print("Directory smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
