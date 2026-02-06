# External Agent Examples

This directory contains examples demonstrating how to build external agents that integrate with Tether.

## Prerequisites

```bash
# Install required dependencies
pip install httpx

# Start Tether agent server
tether-agent
```

## Examples

### REST API Example (`external_agent_example.py`)

Demonstrates using the converged API for:
- Creating sessions with platform binding
- Pushing output via event endpoint
- Requesting approvals via permission_request events
- Polling for user input and permission resolutions

**Run it:**
```bash
python examples/external_agent_example.py
```

## API Overview

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sessions` | POST | Create session (with optional agent_name, platform) |
| `/api/sessions/{id}/events` | POST | Push event (output, status, error, permission_request) |
| `/api/sessions/{id}/events/poll` | GET | Poll for events (user_input, permission_resolved) |
| `/api/sessions/{id}/permission` | POST | Respond to permission request |
| `/api/sessions/{id}/input` | POST | Send user input to session |

### Event Types (POST /api/sessions/{id}/events)

**output** - Send text to UI and bridges:
```json
{"type": "output", "data": {"text": "...", "kind": "step", "is_final": false}}
```

**status** - Transition session state:
```json
{"type": "status", "data": {"status": "awaiting_input"}}
```

**error** - Signal error:
```json
{"type": "error", "data": {"code": "AGENT_ERROR", "message": "..."}}
```

**permission_request** - Request approval:
```json
{"type": "permission_request", "data": {"request_id": "...", "tool_name": "...", "tool_input": {}}}
```

## Example Workflow

```python
import httpx

TETHER = "http://localhost:8787"

async with httpx.AsyncClient() as client:
    # 1. Create session with platform binding
    r = await client.post(f"{TETHER}/api/sessions", json={
        "agent_name": "My Agent",
        "agent_type": "custom",
        "session_name": "My Task",
        "platform": "telegram",
    })
    session_id = r.json()["id"]

    # 2. Push output (auto-transitions CREATED -> RUNNING)
    await client.post(f"{TETHER}/api/sessions/{session_id}/events", json={
        "type": "output",
        "data": {"text": "Working on it..."},
    })

    # 3. Request approval
    await client.post(f"{TETHER}/api/sessions/{session_id}/events", json={
        "type": "permission_request",
        "data": {
            "request_id": "approve_1",
            "tool_name": "Apply changes",
            "tool_input": {"description": "Refactor module"},
        },
    })

    # 4. Poll for resolution
    r = await client.get(f"{TETHER}/api/sessions/{session_id}/events/poll",
        params={"since_seq": 0, "types": "user_input,permission_resolved"})
    events = r.json()["events"]

    # 5. Signal done
    await client.post(f"{TETHER}/api/sessions/{session_id}/events", json={
        "type": "status",
        "data": {"status": "done"},
    })
```

## Platform Integration

When creating a session, specify the platform to auto-create a messaging thread:

```python
{
    "agent_name": "My Agent",
    "agent_type": "custom",
    "session_name": "My Task",
    "platform": "telegram",  # or "slack", "discord"
}
```

All events pushed via `/api/sessions/{id}/events` automatically route to both the UI (via SSE) and the bound messaging platform (via bridge subscriber).

## Next Steps

- See [tests/test_external_agent_api.py](../tests/test_external_agent_api.py) for more examples
- Check [tether/api/sessions.py](../tether/api/sessions.py) for endpoint implementation
