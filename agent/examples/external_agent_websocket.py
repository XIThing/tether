#!/usr/bin/env python3
"""Example external agent using WebSocket API for real-time bidirectional communication.

This demonstrates:
1. Creating a session via REST API
2. Connecting via WebSocket for bidirectional events
3. Sending output, approval requests, and status updates
4. Receiving human input and approval responses in real-time
"""

import asyncio
import json
import sys
import httpx
import websockets


TETHER_API_URL = "http://localhost:8787"
TETHER_WS_URL = "ws://localhost:8787"


async def create_session(client: httpx.AsyncClient) -> dict:
    """Create a new session via REST API."""
    response = await client.post(
        f"{TETHER_API_URL}/external/sessions",
        json={
            "agent_metadata": {
                "name": "WebSocket External Agent",
                "type": "websocket_demo",
                "icon": "⚡",
                "workspace": "demo",
            },
            "session_name": "WebSocket Demo",
            "platform": "telegram",
        },
    )
    response.raise_for_status()
    return response.json()


async def run_agent_via_websocket(session_id: str):
    """Run the agent using WebSocket for bidirectional communication."""
    ws_url = f"{TETHER_WS_URL}/external/sessions/{session_id}/ws"

    async with websockets.connect(ws_url) as websocket:
        print("WebSocket connected!")

        # Send initial output
        await websocket.send(
            json.dumps(
                {
                    "type": "output",
                    "data": {
                        "text": "Hello! I'm connected via WebSocket for real-time communication.",
                    },
                }
            )
        )

        # Update status to thinking
        await websocket.send(
            json.dumps(
                {
                    "type": "status",
                    "data": {"status": "thinking"},
                }
            )
        )
        await asyncio.sleep(1)

        # Send some output
        await websocket.send(
            json.dumps(
                {
                    "type": "output",
                    "data": {
                        "text": "Analyzing the situation...",
                    },
                }
            )
        )
        await asyncio.sleep(1)

        # Update status to executing
        await websocket.send(
            json.dumps(
                {
                    "type": "status",
                    "data": {"status": "executing"},
                }
            )
        )

        # Request approval
        await websocket.send(
            json.dumps(
                {
                    "type": "approval_request",
                    "data": {
                        "title": "Proceed with changes?",
                        "description": "I found 3 optimization opportunities.",
                        "options": ["Approve All", "Review Each", "Cancel"],
                    },
                }
            )
        )

        print("Sent approval request, waiting for response...")

        # Listen for responses
        timeout_seconds = 60
        try:
            async with asyncio.timeout(timeout_seconds):
                async for message in websocket:
                    event = json.loads(message)
                    print(f"Received event: {event}")

                    if event["type"] == "approval_response":
                        choice = event["data"]["choice"]
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "output",
                                    "data": {
                                        "text": f"You selected: {choice}\n\nProceeding accordingly...",
                                    },
                                }
                            )
                        )

                        # Update status to done
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "status",
                                    "data": {"status": "done"},
                                }
                            )
                        )

                        # Final message
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "output",
                                    "data": {
                                        "text": "Task complete! Closing connection.",
                                    },
                                }
                            )
                        )
                        break

                    elif event["type"] == "human_input":
                        text = event["data"]["text"]
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "output",
                                    "data": {
                                        "text": f"I received your message: {text}",
                                    },
                                }
                            )
                        )

        except asyncio.TimeoutError:
            print(f"No response after {timeout_seconds}s, timing out...")
            await websocket.send(
                json.dumps(
                    {
                        "type": "output",
                        "data": {
                            "text": "Timeout waiting for response. Ending session.",
                        },
                    }
                )
            )


async def main():
    """Run the WebSocket example."""
    async with httpx.AsyncClient() as client:
        try:
            # Create session via REST
            print("Creating session...")
            session_data = await create_session(client)
            session_id = session_data["session_id"]
            print(f"Session created: {session_id}")
            print(f"Platform: {session_data['platform']}")

            # Run agent via WebSocket
            await run_agent_via_websocket(session_id)

            # End session
            print("Ending session...")
            response = await client.delete(
                f"{TETHER_API_URL}/external/sessions/{session_id}"
            )
            response.raise_for_status()
            print("Session ended successfully!")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
