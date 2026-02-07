#!/usr/bin/env python3
"""Simple MCP client for testing Tether's MCP server flow.

Starts the MCP server over stdio, creates a session, and lets you:
- send output messages
- receive user input / approval responses
- request approvals
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import anyio
from mcp.client.session import ClientSession
from mcp import types


@dataclass
class ToolResult:
    text: str
    data: Any | None


def _parse_tool_text(text: str) -> ToolResult:
    text = text.strip()
    if not text:
        return ToolResult(text="", data=None)
    # Try JSON first, then python literal (server returns str(dict))
    try:
        return ToolResult(text=text, data=json.loads(text))
    except Exception:
        pass
    try:
        return ToolResult(text=text, data=ast.literal_eval(text))
    except Exception:
        return ToolResult(text=text, data=None)


class RawMcpClient:
    def __init__(
        self,
        proc: subprocess.Popen[str],
        read_stream: anyio.abc.ObjectReceiveStream[str],
        timeout_s: float | None,
        debug: bool,
    ) -> None:
        self._proc = proc
        self._read = read_stream
        self._timeout_s = timeout_s
        self._debug = debug
        self._next_id = 1
        self._pending: deque[dict] = deque()

    async def _send(self, payload: dict) -> None:
        line = json.dumps(payload)
        if self._debug:
            print(f"[debug] -> {line}")
        assert self._proc.stdin is not None
        await anyio.to_thread.run_sync(self._proc.stdin.write, line + "\n")
        await anyio.to_thread.run_sync(self._proc.stdin.flush)

    async def _receive(self) -> dict:
        while True:
            if self._pending:
                return self._pending.popleft()
            line = await self._read.receive()
            try:
                msg = json.loads(line)
            except Exception:
                if self._debug:
                    print(f"[debug] ! invalid json: {line!r}")
                continue
            if self._debug:
                print(f"[debug] <- {msg}")
            return msg

    async def _await_response(self, req_id: int) -> dict:
        while True:
            msg = await self._receive()
            if msg.get("id") == req_id:
                return msg
            self._pending.append(msg)

    async def request(self, method: str, params: dict | None = None) -> dict:
        req_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params

        if self._timeout_s:
            with anyio.fail_after(self._timeout_s):
                await self._send(payload)
                return await self._await_response(req_id)
        await self._send(payload)
        return await self._await_response(req_id)

    async def notify(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if self._timeout_s:
            with anyio.fail_after(self._timeout_s):
                await self._send(payload)
            return
        await self._send(payload)

    async def initialize(self) -> dict:
        result = await self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "tether-mcp-client", "version": "0.1"},
            },
        )
        await self.notify("notifications/initialized")
        return result

    async def call_tool(self, name: str, arguments: dict | None = None) -> ToolResult:
        resp = await self.request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments or {},
            },
        )
        if "error" in resp:
            raise RuntimeError(resp["error"])
        result = resp.get("result", {})
        text_parts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        text = "\n".join(text_parts).strip()
        return _parse_tool_text(text)


async def call_tool_raw(
    client: RawMcpClient,
    name: str,
    arguments: dict | None = None,
    timeout_s: float | None = None,
    debug: bool = False,
) -> ToolResult:
    if debug:
        print(f"[debug] call_tool {name} args={arguments}")
    result = await client.call_tool(name, arguments or {})
    if debug:
        print(f"[debug] call_tool {name} raw_text={result.text}")
    return result


async def call_tool_session(
    session: ClientSession,
    name: str,
    arguments: dict | None = None,
    timeout_s: float | None = None,
    debug: bool = False,
) -> ToolResult:
    if debug:
        print(f"[debug] call_tool {name} args={arguments}")
    if timeout_s:
        with anyio.fail_after(timeout_s):
            result = await session.call_tool(name, arguments or {})
    else:
        result = await session.call_tool(name, arguments or {})
    if debug:
        print(f"[debug] call_tool {name} result={result}")
    text_parts = []
    for item in result.content:
        if isinstance(item, types.TextContent):
            text_parts.append(item.text)
    text = "\n".join(text_parts).strip()
    if debug:
        print(f"[debug] call_tool {name} raw_text={text}")
    return _parse_tool_text(text)


CallToolFn = Callable[[str, dict | None], Awaitable[ToolResult]]


async def poll_inputs(
    call_tool_fn: CallToolFn,
    session_id: str,
    stop_event: anyio.Event,
) -> None:
    since_seq = 0
    while not stop_event.is_set():
        try:
            result = await call_tool_fn(
                "check_input",
                {"session_id": session_id, "since_seq": since_seq},
            )
            payload = result.data or {}
            events = payload.get("events", []) if isinstance(payload, dict) else []
            for evt in events:
                evt_type = evt.get("type")
                seq = evt.get("seq")
                if isinstance(seq, int):
                    since_seq = max(since_seq, seq + 1)
                data = evt.get("data", {})
                if evt_type == "user_input":
                    print(f"\n[user_input] {data.get('text','')}")
                elif evt_type == "permission_resolved":
                    print(
                        f"\n[permission_resolved] allowed={data.get('allowed')} "
                        f"by={data.get('resolved_by')} message={data.get('message')}"
                    )
        except Exception as exc:
            print(f"\n[poll_error] {exc}")

        await anyio.sleep(1.0)


async def interactive_loop(
    call_tool_fn: CallToolFn,
    session_id: str,
) -> None:
    stop_event = anyio.Event()

    async with anyio.create_task_group() as tg:
        tg.start_soon(poll_inputs, call_tool_fn, session_id, stop_event)

        while True:
            try:
                line = await anyio.to_thread.run_sync(input, "> ")
            except (EOFError, KeyboardInterrupt):
                stop_event.set()
                break

            line = line.strip()
            if not line:
                continue

            if line in ("/quit", "/exit"):
                stop_event.set()
                break

            if line == "/help":
                print(
                    "Commands:\n"
                    "  /send <text>          send output to the session\n"
                    "  /ask <title>|<desc>|<opt1,opt2,...>  request approval\n"
                    "  /session              show session id\n"
                    "  /quit                 exit\n"
                    "If no command prefix is used, the line is sent as output."
                )
                continue

            if line == "/session":
                print(session_id)
                continue

            if line.startswith("/send "):
                text = line[len("/send ") :].strip()
                await call_tool_fn(
                    "send_output",
                    {"session_id": session_id, "text": text},
                )
                continue

            if line.startswith("/ask "):
                payload = line[len("/ask ") :].strip()
                try:
                    title, desc, options = payload.split("|", 2)
                except ValueError:
                    print("Format: /ask <title>|<description>|<opt1,opt2,...>")
                    continue
                option_list = [o.strip() for o in options.split(",") if o.strip()]
                await call_tool_fn(
                    "request_approval",
                    {
                        "session_id": session_id,
                        "title": title.strip(),
                        "description": desc.strip(),
                        "options": option_list or ["Allow", "Deny"],
                    },
                )
                continue

            # Default: send output
            await call_tool_fn(
                "send_output",
                {"session_id": session_id, "text": line},
            )

        stop_event.set()
        tg.cancel_scope.cancel()


async def run_scripted(
    call_tool_fn: CallToolFn,
    session_id: str,
) -> None:
    print("[script] send output")
    await call_tool_fn(
        "send_output",
        {"session_id": session_id, "text": "Hello from MCP client"},
    )
    await anyio.sleep(0.5)

    print("[script] request approval")
    await call_tool_fn(
        "request_approval",
        {
            "session_id": session_id,
            "title": "Proceed?",
            "description": "Should I continue the scripted test?",
            "options": ["Yes", "No"],
        },
    )

    print("[script] waiting for approval response or input (10s max)")
    since_seq = 0
    for _ in range(10):
        result = await call_tool_fn(
            "check_input",
            {"session_id": session_id, "since_seq": since_seq},
        )
        payload = result.data or {}
        events = payload.get("events", []) if isinstance(payload, dict) else []
        for evt in events:
            seq = evt.get("seq")
            if isinstance(seq, int):
                since_seq = max(since_seq, seq + 1)
            evt_type = evt.get("type")
            if evt_type == "permission_resolved":
                data = evt.get("data", {})
                print(f"[script] approval resolved: {data}")
                return
            if evt_type == "user_input":
                data = evt.get("data", {})
                print(f"[script] user input: {data}")
                return
        await anyio.sleep(1.0)

    print("[script] no response within 10s")


async def run_inproc(args: argparse.Namespace) -> None:
    os.environ["TETHER_AGENT_PORT"] = str(args.tether_port)
    if args.token:
        os.environ["TETHER_AGENT_TOKEN"] = args.token

    from mcp.server import Server
    from tether.mcp_server.tools import execute_tool, get_tool_definitions

    server = Server("tether-agent")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        tools: list[types.Tool] = []
        for tool in get_tool_definitions():
            tools.append(
                types.Tool(
                    name=tool["name"],
                    description=tool.get("description"),
                    inputSchema=tool["input_schema"],
                )
            )
        return tools

    @server.call_tool()
    async def call_tool_handler(name: str, arguments: dict | None) -> Any:
        return await execute_tool(name, arguments or {})

    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream(0)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream(0)

    async with anyio.create_task_group() as tg:
        tg.start_soon(
            server.run,
            client_to_server_recv,
            server_to_client_send,
            server.create_initialization_options(),
        )

        async with ClientSession(server_to_client_recv, client_to_server_send) as client:
            if args.timeout:
                with anyio.fail_after(args.timeout):
                    await client.initialize()
            else:
                await client.initialize()

            async def call_tool_fn(name: str, arguments: dict | None = None) -> ToolResult:
                return await call_tool_session(
                    client,
                    name,
                    arguments,
                    timeout_s=args.timeout,
                    debug=args.debug,
                )

            result = await call_tool_fn(
                "create_session",
                {
                    "agent_name": args.agent_name,
                    "agent_type": args.agent_type,
                    "session_name": args.session_name,
                    "workspace": args.workspace or None,
                    "platform": args.platform,
                },
            )
            if not isinstance(result.data, dict):
                print(f"Failed to create session: {result.text}")
                return

            session_id = result.data.get("id")
            if not session_id:
                print(f"Failed to create session: {result.text}")
                return

            print(f"Session created: {session_id}")
            if args.mode == "script":
                await run_scripted(call_tool_fn, session_id)
            else:
                print("Type /help for commands.")
                await interactive_loop(call_tool_fn, session_id)


async def _stdout_reader(proc: subprocess.Popen[str], stream: anyio.abc.ObjectSendStream[str]) -> None:
    assert proc.stdout is not None
    try:
        while True:
            line = await anyio.to_thread.run_sync(proc.stdout.readline)
            if not line:
                break
            await stream.send(line.strip())
    finally:
        await stream.aclose()


async def _stderr_reader(proc: subprocess.Popen[str], ready_event: anyio.Event) -> None:
    assert proc.stderr is not None
    try:
        while True:
            line = await anyio.to_thread.run_sync(proc.stderr.readline)
            if not line:
                break
            print(line.rstrip(), file=sys.stderr)
            if "Registered MCP tools" in line:
                ready_event.set()
    finally:
        if not ready_event.is_set():
            ready_event.set()


async def run(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.abspath("agent")
    env["TETHER_AGENT_PORT"] = str(args.tether_port)
    if args.token:
        env["TETHER_AGENT_TOKEN"] = args.token

    if args.debug:
        print(f"[debug] starting MCP server: {args.python} -m tether.mcp_server.server")

    proc = subprocess.Popen(
        [args.python, "-m", "tether.mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=os.getcwd(),
    )

    recv_send, recv_stream = anyio.create_memory_object_stream[str](0)
    async with anyio.create_task_group() as tg:
        ready_event = anyio.Event()
        tg.start_soon(_stdout_reader, proc, recv_send)
        tg.start_soon(_stderr_reader, proc, ready_event)
        if args.timeout:
            with anyio.fail_after(args.timeout):
                await ready_event.wait()
        else:
            await ready_event.wait()
        client = RawMcpClient(proc, recv_stream, args.timeout, args.debug)
        await client.initialize()

        async def call_tool_fn(name: str, arguments: dict | None = None) -> ToolResult:
            return await call_tool_raw(
                client,
                name,
                arguments,
                timeout_s=args.timeout,
                debug=args.debug,
            )

        result = await call_tool_fn(
            "create_session",
            {
                "agent_name": args.agent_name,
                "agent_type": args.agent_type,
                "session_name": args.session_name,
                "workspace": args.workspace or None,
                # Empty string prevents bridge thread creation
                "platform": args.platform,
            },
        )
        if not isinstance(result.data, dict):
            print(f"Failed to create session: {result.text}")
            return

        session_id = result.data.get("id")
        if not session_id:
            print(f"Failed to create session: {result.text}")
            return

        print(f"Session created: {session_id}")
        if args.mode == "script":
            await run_scripted(call_tool_fn, session_id)
        else:
            print("Type /help for commands.")
            await interactive_loop(call_tool_fn, session_id)

        proc.terminate()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCP client for Tether")
    parser.add_argument("--python", default=sys.executable, help="Python executable to start the MCP server")
    parser.add_argument("--tether-port", type=int, default=8787, help="Tether API port")
    parser.add_argument("--token", default=os.environ.get("TETHER_AGENT_TOKEN", ""), help="Tether API token")
    parser.add_argument("--agent-name", default="MCP Client", help="Agent display name")
    parser.add_argument("--agent-type", default="mcp_test", help="Agent type label")
    parser.add_argument("--session-name", default="MCP Test Session", help="Session display name")
    parser.add_argument("--workspace", default=os.getcwd(), help="Workspace directory")
    parser.add_argument("--platform", default="", help="Bridge platform (leave empty for UI-only)")
    parser.add_argument("--timeout", type=float, default=None, help="Timeout in seconds for MCP calls")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--transport",
        choices=["stdio", "inproc"],
        default="stdio",
        help="Transport to use: stdio (default) or inproc",
    )
    parser.add_argument(
        "--mode",
        choices=["interactive", "script"],
        default="interactive",
        help="Run in interactive or scripted mode",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.transport == "inproc":
        anyio.run(run_inproc, args)
    else:
        anyio.run(run, args)


if __name__ == "__main__":
    main()
