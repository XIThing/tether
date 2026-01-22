import express, { Request, Response } from "express";
import { tmpdir } from "node:os";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { Codex } from "../../codex-src/sdk/typescript/src/index.js";
import type {
  ThreadEvent,
  ThreadOptions,
  ThreadItem,
  AgentMessageItem,
  ReasoningItem,
  CommandExecutionItem,
  FileChangeItem,
  McpToolCallItem,
  WebSearchItem,
  TodoListItem,
  ErrorItem,
  Usage,
} from "../../codex-src/sdk/typescript/src/index.js";

const app = express();
app.use(express.json());

type SessionState = {
  id: string;
  thread?: ReturnType<Codex["startThread"]>;
  threadId?: string;
  abortController?: AbortController;
  running: boolean;
  pendingInputs: string[];
  workdir?: string;
  subscribers: Set<Response>;
  heartbeatTimer?: NodeJS.Timeout;
  heartbeatStartMs?: number;
};

// In-memory session state; the agent owns persistence and lifecycle.
const sessions = new Map<string, SessionState>();
const codex = new Codex({
  codexPathOverride: process.env.CODEX_BIN || undefined,
});
const LOG_EVENTS = process.env.SIDECAR_LOG_EVENTS === "1";
const HEARTBEAT_SECONDS = Number(process.env.SIDECAR_HEARTBEAT_SECONDS || "5");

function getSession(sessionId: string): SessionState {
  // Lazily create the session state for a new agent session id.
  let session = sessions.get(sessionId);
  if (!session) {
    session = {
      id: sessionId,
      running: false,
      pendingInputs: [],
      subscribers: new Set(),
    };
    sessions.set(sessionId, session);
  }
  return session;
}

function emit(session: SessionState, event: unknown): void {
  // Emit a JSON SSE event to all subscribers.
  const payload = `data: ${JSON.stringify(event)}\n\n`;
  for (const res of session.subscribers) {
    res.write(payload);
  }
}

function emitOutput(session: SessionState, text: string, kind: "step" | "final"): void {
  emit(session, {
    type: "output",
    data: {
      stream: "combined",
      text,
      kind,
      final: kind === "final",
    },
  });
}

function emitMetadata(session: SessionState, key: string, value: unknown, raw: string): void {
  emit(session, {
    type: "metadata",
    data: { key, value, raw },
  });
}

function emitError(session: SessionState, code: string, message: string): void {
  // Send an error event and log server-side for diagnosis.
  console.error("[sidecar] error", session.id, code, message);
  emit(session, { type: "error", data: { code, message } });
}

function emitHeartbeat(session: SessionState, done: boolean): void {
  const start = session.heartbeatStartMs ?? Date.now();
  const elapsedMs = Math.max(0, Date.now() - start);
  emit(session, {
    type: "heartbeat",
    data: { elapsed_s: elapsedMs / 1000, done },
  });
}

async function ensureWorkdir(session: SessionState): Promise<string> {
  // Each session gets its own temporary working directory.
  if (session.workdir) {
    return session.workdir;
  }
  const dir = await mkdtemp(join(tmpdir(), `tether_${session.id}_`));
  session.workdir = dir;
  return dir;
}

async function clearWorkdir(session: SessionState): Promise<void> {
  // Best-effort cleanup for per-session temp directories.
  if (!session.workdir) {
    return;
  }
  const dir = session.workdir;
  session.workdir = undefined;
  await rm(dir, { recursive: true, force: true });
}

function buildThreadOptions(session: SessionState, approvalChoice: number): ThreadOptions {
  const options: ThreadOptions = {
    workingDirectory: session.workdir,
    skipGitRepoCheck: true,
  };
  if (process.env.CODEX_MODEL) {
    options.model = process.env.CODEX_MODEL;
  }
  if (process.env.CODEX_SANDBOX_MODE) {
    options.sandboxMode = process.env.CODEX_SANDBOX_MODE as ThreadOptions["sandboxMode"];
  }
  if (process.env.CODEX_REASONING_EFFORT) {
    options.modelReasoningEffort =
      process.env.CODEX_REASONING_EFFORT as ThreadOptions["modelReasoningEffort"];
  }
  if (process.env.CODEX_WEB_SEARCH_MODE) {
    options.webSearchMode = process.env.CODEX_WEB_SEARCH_MODE as ThreadOptions["webSearchMode"];
  }
  if (process.env.CODEX_NETWORK_ACCESS_ENABLED) {
    options.networkAccessEnabled = process.env.CODEX_NETWORK_ACCESS_ENABLED === "true";
  }
  if (process.env.CODEX_APPROVAL_POLICY) {
    options.approvalPolicy = process.env.CODEX_APPROVAL_POLICY as ThreadOptions["approvalPolicy"];
  } else if (approvalChoice === 2) {
    options.approvalPolicy = "on-request";
  }
  return options;
}

function emitHeader(session: SessionState, options: ThreadOptions): void {
  const lines = [
    "OpenAI Codex (SDK)",
    "--------",
    `thread id: ${session.threadId ?? "unknown"}`,
    `workdir: ${session.workdir ?? "unknown"}`,
  ];
  if (options.model) {
    lines.push(`model: ${options.model}`);
  }
  if (options.sandboxMode) {
    lines.push(`sandbox: ${options.sandboxMode}`);
  }
  if (options.approvalPolicy) {
    lines.push(`approval: ${options.approvalPolicy}`);
  }
  lines.push("--------");
  emit(session, {
    type: "header",
    data: { text: lines.join("\n") },
  });
}

function emitUsage(session: SessionState, usage: Usage): void {
  const total = usage.input_tokens + usage.cached_input_tokens + usage.output_tokens;
  emitMetadata(session, "input_tokens", usage.input_tokens, String(usage.input_tokens));
  emitMetadata(
    session,
    "cached_input_tokens",
    usage.cached_input_tokens,
    String(usage.cached_input_tokens),
  );
  emitMetadata(session, "output_tokens", usage.output_tokens, String(usage.output_tokens));
  emitMetadata(session, "tokens_used", total, String(total));
}

function emitStepForItem(session: SessionState, item: ThreadItem): void {
  if (!item) {
    return;
  }
  const text = formatStep(item as ThreadItem);
  if (!text) {
    return;
  }
  emitOutput(session, text.endsWith("\n") ? text : `${text}\n`, "step");
}

function formatStep(item: ThreadItem): string {
  switch (item.type) {
    case "reasoning":
      return (item as ReasoningItem).text;
    case "command_execution": {
      const cmd = (item as CommandExecutionItem).command;
      const exit = (item as CommandExecutionItem).exit_code;
      const suffix = exit !== undefined ? ` (exit ${exit})` : "";
      return `Command: ${cmd}${suffix}`;
    }
    case "file_change": {
      const changes = (item as FileChangeItem).changes || [];
      return `File change: ${changes.length} file(s)`;
    }
    case "mcp_tool_call": {
      const mcp = item as McpToolCallItem;
      return `MCP: ${mcp.server}.${mcp.tool}`;
    }
    case "web_search": {
      const web = item as WebSearchItem;
      return `Web search: ${web.query}`;
    }
    case "todo_list": {
      const todo = item as TodoListItem;
      const remaining = todo.items.filter((t) => !t.completed).length;
      return `Todo list: ${remaining} remaining`;
    }
    case "error": {
      const err = item as ErrorItem;
      return `Error: ${err.message}`;
    }
    default:
      return "";
  }
}

async function runTurn(session: SessionState, input: string, approvalChoice: number): Promise<void> {
  session.running = true;
  session.heartbeatStartMs = Date.now();
  if (session.heartbeatTimer) {
    clearInterval(session.heartbeatTimer);
  }
  session.heartbeatTimer = setInterval(() => {
    emitHeartbeat(session, false);
  }, HEARTBEAT_SECONDS * 1000);
  const workdir = await ensureWorkdir(session);
  const options = buildThreadOptions({ ...session, workdir }, approvalChoice);
  if (!session.thread) {
    session.thread = codex.startThread(options);
  }
  session.abortController = new AbortController();
  const { events } = await session.thread.runStreamed(input, {
    signal: session.abortController.signal,
  });
  try {
    for await (const event of events) {
      handleEvent(session, event, options);
    }
  } catch (err) {
    emitError(session, "INTERNAL_ERROR", String(err));
  } finally {
    session.running = false;
    if (session.heartbeatTimer) {
      clearInterval(session.heartbeatTimer);
      session.heartbeatTimer = undefined;
    }
    emitHeartbeat(session, true);
    session.abortController = undefined;
    if (session.heartbeatStartMs) {
      const durationMs = Date.now() - session.heartbeatStartMs;
      emitMetadata(session, "duration_ms", durationMs, String(durationMs));
      session.heartbeatStartMs = undefined;
    }
    const next = session.pendingInputs.shift();
    if (next) {
      void runTurn(session, next, approvalChoice);
    }
  }
}

function handleEvent(session: SessionState, event: ThreadEvent, options: ThreadOptions): void {
  if (LOG_EVENTS) {
    console.log("[sidecar] event", session.id, JSON.stringify(event));
  }
  switch (event.type) {
    case "thread.started":
      session.threadId = event.thread_id;
      emitHeader(session, options);
      break;
    case "item.completed": {
      const item = event.item;
      if (item.type === "agent_message") {
        const msg = (item as AgentMessageItem).text;
        emitOutput(session, msg.endsWith("\n") ? msg : `${msg}\n`, "final");
      } else {
        emitStepForItem(session, item);
      }
      break;
    }
    case "turn.completed":
      emitUsage(session, event.usage);
      break;
    case "turn.failed":
      emitError(session, "INTERNAL_ERROR", event.error.message);
      break;
    case "error":
      emitError(session, "INTERNAL_ERROR", event.message);
      break;
    default:
      break;
  }
}

app.post("/sessions/start", (req: Request, res: Response) => {
  // Start a new Codex exec session for the given agent session id.
  const { session_id, prompt, approval_choice } = req.body || {};
  if (!session_id) {
    return res.status(422).json({ error: "session_id is required" });
  }
  const session = getSession(session_id);
  console.log("[sidecar] start request", session_id);
  session.pendingInputs = [];
  if (session.running) {
    session.pendingInputs.push(String(prompt || ""));
    return res.json({ queued: true });
  }
  if (prompt) {
    void runTurn(session, String(prompt), Number(approval_choice) || 1);
  }
  return res.json({ ok: true });
});

app.post("/sessions/input", (req: Request, res: Response) => {
  // Send or queue follow-up input for a running Codex session.
  const { session_id, text } = req.body || {};
  if (!session_id || !text) {
    return res.status(422).json({ error: "session_id and text are required" });
  }
  const session = getSession(session_id);
  console.log("[sidecar] input", session_id);
  if (session.running) {
    session.pendingInputs.push(String(text));
    return res.json({ queued: true });
  }
  void runTurn(session, String(text), 1);
  return res.json({ ok: true });
});

app.post("/sessions/stop", async (req: Request, res: Response) => {
  // Best-effort stop and cleanup for a session.
  const { session_id } = req.body || {};
  if (!session_id) {
    return res.status(422).json({ error: "session_id is required" });
  }
  const session = getSession(session_id);
  console.log("[sidecar] stop request", session_id);
  if (session.abortController) {
    session.abortController.abort();
  }
  if (session.heartbeatTimer) {
    clearInterval(session.heartbeatTimer);
    session.heartbeatTimer = undefined;
  }
  session.thread = undefined;
  session.threadId = undefined;
  session.running = false;
  session.pendingInputs = [];
  await clearWorkdir(session);
  return res.json({ ok: true });
});

app.get("/events/:sessionId", (req: Request, res: Response) => {
  // SSE endpoint used by the agent to receive output events.
  const session = getSession(req.params.sessionId);
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();

  console.log("[sidecar] sse connect", session.id);
  session.subscribers.add(res);
  req.on("close", () => {
    console.log("[sidecar] sse disconnect", session.id);
    session.subscribers.delete(res);
  });
});

const port = Number(process.env.SIDECAR_PORT || 8788);
app.listen(port, () => {
  console.log(`Codex sidecar listening on http://localhost:${port}`);
});
