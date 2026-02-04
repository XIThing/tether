# External Agent Examples

This directory contains examples demonstrating how to build external agents that integrate with Tether.

## Prerequisites

```bash
# Install required dependencies
pip install httpx websockets

# Start Tether agent server
tether-agent
```

## Examples

### 1. REST API Example (`external_agent_example.py`)

Demonstrates using the REST API for:
- Creating sessions
- Sending output
- Requesting approvals
- Polling for user input
- Proper session cleanup

**Run it:**
```bash
python examples/external_agent_example.py
```

**Key concepts:**
- Session creation with agent metadata
- HTTP polling for user input
- Request/response pattern
- Synchronous workflow

### 2. WebSocket Example (`external_agent_websocket.py`)

Demonstrates real-time bidirectional communication:
- WebSocket connection for live events
- Sending status updates (thinking, executing, done)
- Approval requests with real-time responses
- Handling human input messages

**Run it:**
```bash
python examples/external_agent_websocket.py
```

**Key concepts:**
- Real-time event streaming
- Bidirectional communication
- Status updates
- Asynchronous message handling

## API Overview

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/external/sessions` | POST | Create a new session |
| `/external/sessions/{id}/output` | POST | Send output text |
| `/external/sessions/{id}/approval` | POST | Request approval |
| `/external/sessions/{id}/input` | GET | Poll for user input |
| `/external/sessions/{id}` | DELETE | End session |

### WebSocket Events

**Agent → Tether:**
- `output` - Send text to user
- `approval_request` - Request user approval
- `status` - Update agent status (thinking/executing/done/error)

**Tether → Agent:**
- `human_input` - User sent a message
- `approval_response` - User responded to approval

## Example Workflows

### Basic Task Execution

```python
# 1. Create session
session = await create_session(client)

# 2. Send updates
await send_output(client, session["session_id"], "Working on task...")

# 3. Request approval
await request_approval(
    client,
    session["session_id"],
    title="Ready to commit?",
    description="Changes are ready",
    options=["Approve", "Reject"]
)

# 4. Check for response
response = await check_input(client, session["session_id"])

# 5. Cleanup
await end_session(client, session["session_id"])
```

### Real-time WebSocket Agent

```python
# Connect to WebSocket
async with websockets.connect(ws_url) as ws:
    # Send events
    await ws.send(json.dumps({
        "type": "output",
        "data": {"text": "Processing..."}
    }))

    # Receive events
    async for message in ws:
        event = json.loads(message)
        if event["type"] == "human_input":
            # Handle user message
            pass
```

## Platform Integration

When creating a session, specify the platform:

```python
{
    "platform": "telegram",  # or "slack", "discord"
    "session_name": "My Task",
    "agent_metadata": {
        "name": "My Agent",
        "type": "custom",
        "icon": "🤖"
    }
}
```

The session will automatically create a thread on the specified platform, and all outputs/approvals will be routed there.

## Error Handling

Always handle errors gracefully:

```python
try:
    response = await client.post(url, json=data)
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    print(f"API error: {e.response.status_code}")
    print(f"Details: {e.response.text}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Next Steps

- Read the [main README](../README.md) for full API documentation
- Check [tether/api/external_agents.py](../tether/api/external_agents.py) for implementation details
- See [tests/test_external_agent_api.py](../tests/test_external_agent_api.py) for more examples
- Join discussions at https://github.com/XIThing/tether/discussions

## Contributing

Have an example to share? Submit a PR with:
1. The example script
2. Documentation in this README
3. Any required dependencies

## License

Apache 2.0 - same as Tether Agent
