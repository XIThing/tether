#!/usr/bin/env python3
"""Example external agent using Tether's External Agent API.

This demonstrates how to create a simple external agent that:
1. Creates a session
2. Sends output to the user
3. Requests approvals
4. Receives input from the user
5. Properly handles cleanup
"""

import asyncio
import httpx
import sys

TETHER_API_URL = "http://localhost:8787"


async def create_session(client: httpx.AsyncClient) -> dict:
    """Create a new session for this external agent."""
    response = await client.post(
        f"{TETHER_API_URL}/external/sessions",
        json={
            "agent_metadata": {
                "name": "Example External Agent",
                "type": "custom",
                "icon": "🤖",
                "workspace": "demo",
            },
            "session_name": "Demo Task",
            "platform": "telegram",  # or "slack", "discord"
        },
    )
    response.raise_for_status()
    return response.json()


async def send_output(client: httpx.AsyncClient, session_id: str, text: str) -> None:
    """Send output text to the user."""
    response = await client.post(
        f"{TETHER_API_URL}/external/sessions/{session_id}/output",
        json={"text": text},
    )
    response.raise_for_status()


async def request_approval(
    client: httpx.AsyncClient,
    session_id: str,
    title: str,
    description: str,
    options: list[str],
) -> dict:
    """Request approval from the user."""
    response = await client.post(
        f"{TETHER_API_URL}/external/sessions/{session_id}/approval",
        json={
            "title": title,
            "description": description,
            "options": options,
        },
    )
    response.raise_for_status()
    return response.json()


async def check_input(
    client: httpx.AsyncClient, session_id: str, timeout: int = 30
) -> dict | None:
    """Poll for user input (non-blocking with timeout)."""
    try:
        response = await client.get(
            f"{TETHER_API_URL}/external/sessions/{session_id}/input",
            params={"timeout": timeout},
            timeout=timeout + 5,  # Add buffer to HTTP timeout
        )
        response.raise_for_status()
        data = response.json()
        return data if data else None
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 204:
            return None  # No input available
        raise


async def end_session(client: httpx.AsyncClient, session_id: str) -> None:
    """End the session and cleanup."""
    response = await client.delete(
        f"{TETHER_API_URL}/external/sessions/{session_id}"
    )
    response.raise_for_status()


async def main():
    """Run the example external agent."""
    async with httpx.AsyncClient() as client:
        try:
            # Create session
            print("Creating session...")
            session_data = await create_session(client)
            session_id = session_data["session_id"]
            print(f"Session created: {session_id}")
            print(f"Platform: {session_data['platform']}")
            print(f"Thread info: {session_data['thread_info']}")

            # Send initial output
            await send_output(
                client,
                session_id,
                "Hello! I'm an external agent. I'm going to demonstrate some capabilities.",
            )
            await asyncio.sleep(1)

            # Send status update
            await send_output(client, session_id, "Status: thinking 💭")
            await asyncio.sleep(2)

            # Send some output
            await send_output(
                client,
                session_id,
                "I've analyzed the codebase and have some suggestions...",
            )
            await asyncio.sleep(1)

            # Request approval
            print("Requesting approval...")
            approval_data = await request_approval(
                client,
                session_id,
                title="Approve Changes?",
                description="I'm ready to apply the suggested refactoring.",
                options=["Approve", "Reject", "Show Details"],
            )
            print(f"Approval requested: {approval_data['request_id']}")

            # Wait for approval response
            print("Waiting for approval response...")
            while True:
                user_input = await check_input(client, session_id, timeout=30)
                if user_input:
                    print(f"Received input: {user_input}")
                    if user_input["type"] == "approval_response":
                        choice = user_input["data"]["choice"]
                        await send_output(
                            client,
                            session_id,
                            f"You selected: {choice}",
                        )
                        break
                else:
                    print("No input yet, waiting...")

            # Final output
            await send_output(
                client,
                session_id,
                "Task complete! This session will end in 5 seconds.",
            )
            await asyncio.sleep(5)

            # End session
            print("Ending session...")
            await end_session(client, session_id)
            print("Session ended successfully!")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
