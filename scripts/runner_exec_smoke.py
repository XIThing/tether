#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import sys
import time
from typing import Dict, Optional
from urllib.parse import urlparse


def build_headers(token: str) -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def request_json(base: str, method: str, path: str, token: str, payload: Optional[dict] = None) -> dict:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80)
    body = None
    headers = build_headers(token)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    if resp.status < 200 or resp.status >= 300:
        raise RuntimeError(f"{method} {path} failed: {resp.status} {data}")
    return json.loads(data) if data else {}


def sse_read_output(base: str, session_id: str, token: str, timeout_s: int, require_text: Optional[str] = None) -> str:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout_s)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("GET", f"/events/sessions/{session_id}", headers=headers)
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


def poll_session(base: str, session_id: str, token: str, timeout_s: int) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        try:
            data = request_json(base, "GET", f"/api/sessions/{session_id}", token)
        except Exception as exc:
            print(f"[poll] error: {exc}")
            time.sleep(2)
            continue
        session = data.get("session", {})
        print(
            f"[poll] state={session.get('state')} last_activity={session.get('last_activity_at')} exit={session.get('exit_code')}"
        )
        if session.get("state") in ("STOPPED", "ERROR"):
            return
        time.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner exec smoke test via API endpoints")
    parser.add_argument("--base-url", default="http://localhost:8787")
    parser.add_argument("--token", default="")
    parser.add_argument("--prompt", default="Remember 888.")
    parser.add_argument("--followup", default="What do you remember?")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token

    session = request_json(base, "POST", "/api/sessions", token, {"repo_id": "repo_exec_smoke"})
    session_id = session["session"]["id"]

    request_json(
        base,
        "POST",
        f"/api/sessions/{session_id}/start",
        token,
        {"prompt": args.prompt, "approval_choice": 1},
    )

    try:
        first = sse_read_output(base, session_id, token, args.timeout, require_text="got it")
        print("First output:")
        print(first)
    except Exception as exc:
        print(f"First output error: {exc}")
        poll_session(base, session_id, token, args.timeout)
        raise

    request_json(
        base,
        "POST",
        f"/api/sessions/{session_id}/input",
        token,
        {"text": args.followup},
    )

    try:
        second = sse_read_output(base, session_id, token, args.timeout, require_text="888")
        if not second.strip():
            raise RuntimeError("Second output was empty")
        print("Second output:")
        print(second)
    except Exception as exc:
        print(f"Second output error: {exc}")
        poll_session(base, session_id, token, args.timeout)
        raise

    request_json(base, "POST", f"/api/sessions/{session_id}/stop", token)
    print("Smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
