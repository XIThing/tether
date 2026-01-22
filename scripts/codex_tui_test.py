#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import sys
import threading
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


def sse_consumer(base: str, session_id: str, token: str, stop_event: threading.Event) -> None:
    url = urlparse(base)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("GET", f"/events/sessions/{session_id}", headers=headers)
    resp = conn.getresponse()
    if resp.status != 200:
        data = resp.read().decode("utf-8")
        conn.close()
        print(f"SSE connection failed: {resp.status} {data}", file=sys.stderr)
        return

    try:
        while not stop_event.is_set():
            line = resp.fp.readline()
            if not line:
                time.sleep(0.05)
                continue
            if line == b"\n":
                continue
            if line.startswith(b"data: "):
                payload = line[6:].decode("utf-8", errors="replace").strip()
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "output":
                    text = event.get("data", {}).get("text", "")
                    sys.stdout.write(text)
                    sys.stdout.flush()
                elif event.get("type") == "error":
                    print(f"\n[error] {event.get('data')}", file=sys.stderr)
                else:
                    pass
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive Codex TUI test via API endpoints")
    parser.add_argument("--base-url", default="http://localhost:8787")
    parser.add_argument("--token", default="")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--approval-choice", type=int, default=1)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token

    session = request_json(base, "POST", "/api/sessions", token, {"repo_id": "repo_tui_test"})
    session_id = session["session"]["id"]

    request_json(
        base,
        "POST",
        f"/api/sessions/{session_id}/start",
        token,
        {"prompt": args.prompt, "approval_choice": args.approval_choice},
    )

    stop_event = threading.Event()
    thread = threading.Thread(target=sse_consumer, args=(base, session_id, token, stop_event), daemon=True)
    thread.start()

    print("\nType input to send to Codex. Ctrl+C to stop.\n")
    try:
        for line in sys.stdin:
            text = line.strip()
            if not text:
                continue
            request_json(base, "POST", f"/api/sessions/{session_id}/input", token, {"text": text})
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        try:
            request_json(base, "POST", f"/api/sessions/{session_id}/stop", token)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
