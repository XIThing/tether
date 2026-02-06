#!/usr/bin/env python3
"""Example external agent using Tether's API.

This demonstrates how to create a simple external agent that:
1. Creates a session with platform binding
2. Sends output via event push
3. Requests approvals via permission_request events
4. Polls for user input and permission resolutions
"""

import asyncio
import httpx
import sys

TETHER_URL = "http://localhost:8787"
TOKEN = ""  # Set if TETHER_AUTH_TOKEN is configured


def headers() -> dict:
    if TOKEN:
        return {"Authorization": f"Bearer {TOKEN}"}
    return {}


async def main():
    """Run the example external agent."""
    async with httpx.AsyncClient() as client:
        try:
            # 1. Create session
            print("Creating session...")
            response = await client.post(
                f"{TETHER_URL}/api/sessions",
                headers=headers(),
                json={
                    "agent_name": "Example Agent",
                    "agent_type": "custom",
                    "session_name": "Demo Task",
                    "platform": "telegram",
                },
            )
            response.raise_for_status()
            session = response.json()
            session_id = session["id"]
            print(f"Session created: {session_id}")
            print(f"Platform: {session.get('platform')}")

            # 2. Send output (auto-transitions CREATED -> RUNNING)
            await client.post(
                f"{TETHER_URL}/api/sessions/{session_id}/events",
                headers=headers(),
                json={
                    "type": "output",
                    "data": {"text": "Hello! I'm analyzing the codebase..."},
                },
            )
            await asyncio.sleep(2)

            # 3. Send more output
            await client.post(
                f"{TETHER_URL}/api/sessions/{session_id}/events",
                headers=headers(),
                json={
                    "type": "output",
                    "data": {"text": "Found some improvements to suggest."},
                },
            )
            await asyncio.sleep(1)

            # 4. Request approval
            print("Requesting approval...")
            await client.post(
                f"{TETHER_URL}/api/sessions/{session_id}/events",
                headers=headers(),
                json={
                    "type": "permission_request",
                    "data": {
                        "request_id": "approve_refactor",
                        "tool_name": "Apply refactoring",
                        "tool_input": {
                            "description": "Refactor auth module to use dependency injection",
                        },
                    },
                },
            )

            # 5. Poll for resolution
            print("Waiting for approval...")
            last_seq = 0
            while True:
                response = await client.get(
                    f"{TETHER_URL}/api/sessions/{session_id}/events/poll",
                    headers=headers(),
                    params={
                        "since_seq": last_seq,
                        "types": "user_input,permission_resolved",
                    },
                )
                data = response.json()
                for evt in data.get("events", []):
                    print(f"Received: {evt}")
                    if evt.get("seq"):
                        last_seq = evt["seq"]
                    if evt["type"] == "permission_resolved":
                        print(f"Permission resolved: {evt['data']}")
                        break
                else:
                    await asyncio.sleep(2)
                    continue
                break

            # 6. Signal done
            await client.post(
                f"{TETHER_URL}/api/sessions/{session_id}/events",
                headers=headers(),
                json={
                    "type": "output",
                    "data": {"text": "Task complete!", "is_final": True},
                },
            )
            await client.post(
                f"{TETHER_URL}/api/sessions/{session_id}/events",
                headers=headers(),
                json={
                    "type": "status",
                    "data": {"status": "done"},
                },
            )
            print("Done!")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
