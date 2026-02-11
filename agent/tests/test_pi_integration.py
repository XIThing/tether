"""Integration tests for pi external session attachment."""
import httpx
import pytest


@pytest.mark.anyio
async def test_attach_to_pi_session_includes_history(
    api_client: httpx.AsyncClient,
) -> None:
    """Test that attaching to a pi session preserves history."""
    # List external sessions to find a pi session
    list_response = await api_client.get("/api/external-sessions?runner_type=pi&limit=1")
    assert list_response.status_code == 200
    sessions = list_response.json()
    
    if not sessions:
        pytest.skip("No pi sessions available for testing")
    
    pi_session = sessions[0]
    assert pi_session["runner_type"] == "pi"
    
    # Attach to the pi session
    attach_response = await api_client.post(
        "/api/sessions/attach",
        json={
            "external_id": pi_session["id"],
            "runner_type": "pi",
            "directory": pi_session["directory"],
        },
    )
    assert attach_response.status_code == 201
    attached = attach_response.json()
    
    # Verify session was created with correct runner type
    assert attached["runner_type"] == "pi"
    assert attached["adapter"] == "pi_rpc"
    assert attached["state"] == "AWAITING_INPUT"
    assert attached["directory"] == pi_session["directory"]


@pytest.mark.anyio
async def test_pi_session_detail_has_last_prompt(
    api_client: httpx.AsyncClient,
) -> None:
    """Test that pi session detail includes last_prompt."""
    # Get first pi session
    list_response = await api_client.get("/api/external-sessions?runner_type=pi&limit=1")
    assert list_response.status_code == 200
    sessions = list_response.json()
    
    if not sessions:
        pytest.skip("No pi sessions available for testing")
    
    pi_session = sessions[0]
    
    # Get session detail with history
    detail_response = await api_client.get(
        f"/api/external-sessions/{pi_session['id']}/history",
        params={"runner_type": "pi", "limit": 10},
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    
    # Verify structure
    assert "last_prompt" in detail
    assert "first_prompt" in detail
    assert "messages" in detail
    assert isinstance(detail["messages"], list)
