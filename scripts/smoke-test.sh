#!/bin/bash
# Smoke test for Tether
# Verifies the agent is running and responding

set -e

BASE_URL="${1:-http://localhost:8787}"
AUTH_HEADER=""

# Use token if set
if [ -n "$TETHER_AGENT_TOKEN" ]; then
    AUTH_HEADER="Authorization: Bearer $TETHER_AGENT_TOKEN"
fi

echo "Testing Tether at $BASE_URL"
echo

# Test health endpoint (no auth required)
echo -n "Health check... "
HEALTH=$(curl -sf "$BASE_URL/api/health" 2>/dev/null) || {
    echo "FAILED"
    echo "Could not reach $BASE_URL/api/health"
    echo "Is the agent running? Try: make start"
    exit 1
}
echo "OK"
echo "  $HEALTH"

# Test sessions endpoint (may require auth)
echo -n "Sessions API... "
if [ -n "$AUTH_HEADER" ]; then
    SESSIONS=$(curl -sf -H "$AUTH_HEADER" "$BASE_URL/api/sessions" 2>/dev/null)
else
    SESSIONS=$(curl -sf "$BASE_URL/api/sessions" 2>/dev/null)
fi
RESULT=$?
if [ $RESULT -ne 0 ]; then
    # Check if it's an auth issue
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/sessions" 2>/dev/null)
    if [ "$STATUS" = "401" ]; then
        echo "FAILED (auth required)"
        echo "Set TETHER_AGENT_TOKEN and try again"
    else
        echo "FAILED"
        echo "Could not reach $BASE_URL/api/sessions"
    fi
    exit 1
fi
echo "OK"

# Test UI loads
echo -n "UI available... "
UI=$(curl -sf "$BASE_URL/" -o /dev/null -w "%{http_code}" 2>/dev/null) || UI="000"
if [ "$UI" = "200" ]; then
    echo "OK"
else
    echo "FAILED (HTTP $UI)"
    exit 1
fi

echo
echo "All checks passed!"
