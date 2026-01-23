#!/usr/bin/env python3
"""Smoke test for the Claude runner (Anthropic API).

Runs a multi-turn conversation test:
1. Ask Claude to remember a random number
2. Ask Claude to repeat it back
3. Verify the response

Requires: ANTHROPIC_API_KEY environment variable
"""

import asyncio
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TETHER_AGENT_DEV_MODE", "1")
os.environ.setdefault("TETHER_AGENT_ADAPTER", "claude")


class Events:
    """Collects runner events."""

    def __init__(self):
        self.outputs = []
        self.errors = []
        self.awaiting_input = False

    async def on_output(self, session_id, stream, text, kind=None, is_final=None):
        self.outputs.append(text)
        print(text, end="", flush=True)

    async def on_error(self, session_id, code, message):
        self.errors.append(f"{code}: {message}")
        print(f"\n[ERROR] {code}: {message}")

    async def on_metadata(self, session_id, key, value, raw):
        pass

    async def on_heartbeat(self, session_id, elapsed_s, done):
        pass

    async def on_exit(self, session_id, exit_code):
        pass

    async def on_awaiting_input(self, session_id):
        self.awaiting_input = True

    def get_text(self):
        return "".join(self.outputs)

    def reset(self):
        self.outputs = []
        self.errors = []
        self.awaiting_input = False


async def wait_for_turn(events, timeout=60):
    """Wait for the current turn to complete."""
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(0.5)
        elapsed += 0.5
        if events.awaiting_input or events.errors:
            return
    raise TimeoutError("Turn timed out")


async def run_test():
    from tether.runner.claude import ClaudeRunner
    from tether.settings import settings
    from tether import store as store_module
    import importlib

    # Check API key
    if not settings.anthropic_api_key():
        print("ERROR: ANTHROPIC_API_KEY not set")
        return False

    print(f"Model: {settings.claude_model()}")
    print()

    events = Events()
    runner = ClaudeRunner(events)
    secret = random.randint(100, 999)

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["TETHER_AGENT_DATA_DIR"] = tmpdir
        importlib.reload(store_module)
        from tether.store import store

        session = store.create_session("test", "main")
        session.state = store_module.SessionState.RUNNING
        store.update_session(session)
        store.set_workdir(session.id, tmpdir, managed=False)

        # Turn 1: Remember number
        print(f"=== Turn 1: Remember {secret} ===")
        await runner.start(
            session.id,
            f"Remember this number: {secret}. Reply only with 'OK'.",
            approval_choice=0
        )
        await wait_for_turn(events)
        print("\n")

        if events.errors:
            return False

        # Turn 2: Recall number
        events.reset()
        print("=== Turn 2: What was the number? ===")
        await runner.send_input(session.id, "What number did I ask you to remember? Reply with just the number.")
        await wait_for_turn(events)
        print("\n")

        if events.errors:
            return False

        response = events.get_text()
        if str(secret) in response:
            print(f"PASS: Claude remembered {secret}")
            await runner.stop(session.id)
            return True
        else:
            print(f"FAIL: Expected {secret} in response")
            await runner.stop(session.id)
            return False


def main():
    print("=" * 50)
    print("Claude Runner Smoke Test (Anthropic API)")
    print("=" * 50)
    print()

    try:
        success = asyncio.run(run_test())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
