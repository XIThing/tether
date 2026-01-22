import asyncio
import contextlib

import httpx
import pytest

from tether.main import app
from tether.store import store


@pytest.mark.anyio
async def test_start_session_send_input_get_output(tmp_path, monkeypatch) -> None:
    script_path = tmp_path / "fake_codex.py"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "",
                "args = sys.argv[1:]",
                "if args and args[0] == 'exec':",
                "    filtered = []",
                "    skip_next = False",
                "    for arg in args[1:]:",
                "        if skip_next:",
                "            skip_next = False",
                "            continue",
                "        if arg.startswith('--'):",
                "            skip_next = True",
                "            continue",
                "        filtered.append(arg)",
                "    args = ['exec'] + filtered",
                "if args[:2] == ['exec', 'resume']:",
                "    sess_id = args[2]",
                "    prompt = ' '.join(args[3:])",
                "    print(f'Resumed {sess_id}', flush=True)",
                "    if prompt == 'next':",
                "        print('OUTPUT: next ok', flush=True)",
                "    sys.exit(0)",
                "if args and args[0] == 'exec':",
                "    prompt = ' '.join(args[1:])",
                "    print('Session ID: sess_test_123', flush=True)",
                "    if prompt == 'hello':",
                "        print('OUTPUT: hi', flush=True)",
                "    sys.exit(0)",
                "print('Unknown args', flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    monkeypatch.setenv("CODEX_BIN", str(script_path))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/sessions", json={"repo_id": "repo_test"})
        session_id = response.json()["session"]["id"]

        queue = store.new_subscriber(session_id)
        try:
            await client.post(
                f"/api/sessions/{session_id}/start",
                json={"prompt": "hello", "approval_choice": 1},
            )

            found_hi = False
            found_next = False
            sent_next = False
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 8

            while loop.time() < deadline:
                remaining = deadline - loop.time()
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if event.get("type") == "output" and "OUTPUT: hi" in event.get("data", {}).get("text", ""):
                    found_hi = True
                    if not sent_next:
                        await client.post(
                            f"/api/sessions/{session_id}/input",
                            json={"text": "next"},
                        )
                        sent_next = True
                if event.get("type") == "output" and "OUTPUT: next ok" in event.get("data", {}).get("text", ""):
                    found_next = True
                if found_hi and found_next:
                    break

            assert found_hi, "expected output for first prompt"
            assert found_next, "expected output for follow-up input"
        finally:
            await client.post(f"/api/sessions/{session_id}/stop")
            store.remove_subscriber(session_id, queue)
