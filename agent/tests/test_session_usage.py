"""Tests for SessionStore.session_usage aggregation."""

import json
import os

import pytest

from tether.store import SessionStore


class TestSessionUsage:
    """Test session_usage reads and aggregates metadata events."""

    def _write_events(self, store: SessionStore, session_id: str, events: list[dict]) -> None:
        """Write events directly to the JSONL file."""
        path = os.path.join(store._data_dir, "sessions", session_id, "events.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

    def test_empty_event_log(self, fresh_store: SessionStore) -> None:
        """Returns zeros for a session with no events."""
        session = fresh_store.create_session("test", "main")
        usage = fresh_store.session_usage(session.id)
        assert usage == {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}

    def test_nonexistent_session(self, fresh_store: SessionStore) -> None:
        """Returns zeros for a session that doesn't exist."""
        usage = fresh_store.session_usage("nonexistent_session")
        assert usage == {"input_tokens": 0, "output_tokens": 0, "total_cost_usd": 0.0}

    def test_aggregates_token_events(self, fresh_store: SessionStore) -> None:
        """Sums token counts from multiple metadata events."""
        session = fresh_store.create_session("test", "main")
        self._write_events(fresh_store, session.id, [
            {"type": "metadata", "data": {"key": "tokens", "value": {"input": 100, "output": 50}}},
            {"type": "metadata", "data": {"key": "tokens", "value": {"input": 200, "output": 75}}},
        ])
        usage = fresh_store.session_usage(session.id)
        assert usage["input_tokens"] == 300
        assert usage["output_tokens"] == 125

    def test_aggregates_cost_events(self, fresh_store: SessionStore) -> None:
        """Sums cost from multiple metadata events."""
        session = fresh_store.create_session("test", "main")
        self._write_events(fresh_store, session.id, [
            {"type": "metadata", "data": {"key": "cost", "value": 0.01}},
            {"type": "metadata", "data": {"key": "cost", "value": 0.02}},
        ])
        usage = fresh_store.session_usage(session.id)
        assert usage["total_cost_usd"] == 0.03

    def test_ignores_non_metadata_events(self, fresh_store: SessionStore) -> None:
        """Only processes metadata events, ignores output/status."""
        session = fresh_store.create_session("test", "main")
        self._write_events(fresh_store, session.id, [
            {"type": "output", "data": {"text": "hello"}},
            {"type": "metadata", "data": {"key": "tokens", "value": {"input": 100, "output": 50}}},
            {"type": "status", "data": {"status": "running"}},
        ])
        usage = fresh_store.session_usage(session.id)
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50

    def test_ignores_non_token_metadata(self, fresh_store: SessionStore) -> None:
        """Ignores metadata events with unknown keys."""
        session = fresh_store.create_session("test", "main")
        self._write_events(fresh_store, session.id, [
            {"type": "metadata", "data": {"key": "model", "value": "claude-3.5-sonnet"}},
            {"type": "metadata", "data": {"key": "tokens", "value": {"input": 100, "output": 50}}},
        ])
        usage = fresh_store.session_usage(session.id)
        assert usage["input_tokens"] == 100

    def test_mixed_tokens_and_cost(self, fresh_store: SessionStore) -> None:
        """Handles both token and cost events together."""
        session = fresh_store.create_session("test", "main")
        self._write_events(fresh_store, session.id, [
            {"type": "metadata", "data": {"key": "tokens", "value": {"input": 500, "output": 200}}},
            {"type": "metadata", "data": {"key": "cost", "value": 0.005}},
            {"type": "metadata", "data": {"key": "tokens", "value": {"input": 300, "output": 100}}},
            {"type": "metadata", "data": {"key": "cost", "value": 0.003}},
        ])
        usage = fresh_store.session_usage(session.id)
        assert usage["input_tokens"] == 800
        assert usage["output_tokens"] == 300
        assert usage["total_cost_usd"] == 0.008

    def test_handles_malformed_lines(self, fresh_store: SessionStore) -> None:
        """Skips malformed JSON lines gracefully."""
        session = fresh_store.create_session("test", "main")
        path = os.path.join(fresh_store._data_dir, "sessions", session.id, "events.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("not valid json\n")
            f.write(json.dumps({"type": "metadata", "data": {"key": "tokens", "value": {"input": 100, "output": 50}}}) + "\n")
            f.write("\n")  # blank line

        usage = fresh_store.session_usage(session.id)
        assert usage["input_tokens"] == 100

    def test_cost_rounding(self, fresh_store: SessionStore) -> None:
        """Cost is rounded to 4 decimal places."""
        session = fresh_store.create_session("test", "main")
        self._write_events(fresh_store, session.id, [
            {"type": "metadata", "data": {"key": "cost", "value": 0.00001}},
            {"type": "metadata", "data": {"key": "cost", "value": 0.00002}},
            {"type": "metadata", "data": {"key": "cost", "value": 0.00003}},
        ])
        usage = fresh_store.session_usage(session.id)
        assert usage["total_cost_usd"] == 0.0001
