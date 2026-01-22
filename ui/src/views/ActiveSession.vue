<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-stone-800/70 bg-stone-900/70 p-4 shadow-sm">
      <div class="flex flex-1 flex-col gap-1">
        <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.3em] text-stone-400">
          <span class="h-2.5 w-2.5 rounded-full" :class="statusDot"></span>
          <p>Active session</p>
        </div>
        <p v-if="session" class="text-lg font-semibold text-stone-50">
          {{ session.name || session.repo_display }}
        </p>
        <div v-else class="text-sm text-stone-500">Creating a fresh session...</div>
        <div v-if="session" class="flex flex-wrap items-center gap-3 text-xs text-stone-400">
          <span>{{ session.directory || session.repo_display }}</span>
          <Badge
            v-if="session.directory_has_git"
            variant="outline"
            class="text-[10px] uppercase tracking-[0.2em] text-emerald-300"
          >
            Git repo
          </Badge>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Tabs v-model="viewMode" class="w-auto">
          <TabsList class="bg-stone-900">
            <TabsTrigger value="chat">Chat</TabsTrigger>
            <TabsTrigger value="diff" :disabled="!(session?.directory_has_git || diff)">
              Diff
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <Button variant="ghost" size="icon" @click="toggleInfo">
          <Info class="h-4 w-4" />
        </Button>
        <Button variant="destructive" size="sm" @click="stop" :disabled="!canStop">
          Stop
        </Button>
      </div>
    </div>

    <Card v-if="infoOpen" class="border-stone-800/70 bg-stone-900/70">
      <CardHeader class="flex flex-col gap-3 p-4">
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm uppercase tracking-[0.3em] text-stone-400">Session info</CardTitle>
          <Button size="sm" variant="ghost" @click="infoOpen = false">Close</Button>
        </div>
        <div class="flex flex-wrap gap-3 text-[11px] uppercase tracking-[0.2em] text-stone-400">
          <div class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2">
            <p>Directory</p>
            <p class="mt-1 max-w-[20ch] break-all text-xs font-semibold text-stone-50">
              {{ session?.directory || session?.repo_display || "Temporary workspace" }}
            </p>
          </div>
          <div
            v-if="session?.directory_has_git"
            class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2 text-emerald-300"
          >
            <p>Git</p>
            <p class="mt-1 text-xs font-semibold">Detected</p>
          </div>
        </div>
      </CardHeader>
      <CardContent class="space-y-4 p-4">
        <div v-if="headerInfo" class="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2">
            <p class="text-[10px] uppercase tracking-[0.2em] text-stone-400">Version</p>
            <p class="mt-1 text-xs font-semibold text-stone-50">{{ headerInfo.version }}</p>
          </div>
          <div class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2">
            <p class="text-[10px] uppercase tracking-[0.2em] text-stone-400">Model</p>
            <p class="mt-1 text-xs font-semibold text-stone-50">{{ headerInfo.model }}</p>
          </div>
          <div class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2">
            <p class="text-[10px] uppercase tracking-[0.2em] text-stone-400">Provider</p>
            <p class="mt-1 text-xs font-semibold text-stone-50">{{ headerInfo.provider }}</p>
          </div>
          <div class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2">
            <p class="text-[10px] uppercase tracking-[0.2em] text-stone-400">Approval</p>
            <p class="mt-1 text-xs font-semibold text-stone-50">{{ headerInfo.approval }}</p>
          </div>
          <div class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2">
            <p class="text-[10px] uppercase tracking-[0.2em] text-stone-400">Sandbox</p>
            <p class="mt-1 text-xs font-semibold text-stone-50">{{ headerInfo.sandbox }}</p>
          </div>
          <div class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2">
            <p class="text-[10px] uppercase tracking-[0.2em] text-stone-400">Session ID</p>
            <p class="mt-1 break-all font-mono text-xs font-semibold text-stone-50">
              {{ headerInfo.sessionId }}
            </p>
          </div>
        </div>
        <p v-else class="text-sm text-stone-500">No header yet.</p>
        <details
          v-if="session?.codex_header"
          class="rounded-xl border border-stone-700/80 bg-stone-900/40 px-3 py-2 text-stone-200"
        >
          <summary class="cursor-pointer text-xs font-semibold uppercase tracking-[0.2em] text-stone-400">
            Raw header
          </summary>
          <pre class="mt-2 whitespace-pre-wrap font-mono text-xs text-stone-300">
{{ session.codex_header }}
          </pre>
        </details>
        <div class="space-y-2">
          <label class="text-xs font-semibold uppercase tracking-[0.3em] text-stone-400">Session name</label>
          <div class="flex gap-2">
            <Input v-model="renameValue" class="flex-1" placeholder="Session name" />
            <Button size="sm" @click="applyRename" :disabled="renaming || !renameValue.trim()">Save</Button>
          </div>
          <p v-if="renameMessage" :class="renameMessage === 'Updated' ? 'text-emerald-400' : 'text-rose-400'">
            {{ renameMessage }}
          </p>
        </div>
      </CardContent>
    </Card>

    <Card v-if="viewMode === 'chat'" class="border-stone-800/60 bg-stone-900/70">
      <CardContent class="space-y-4 p-4">
        <div class="min-h-[50vh] space-y-3">
          <p v-if="!messages.length" class="text-center text-sm text-stone-500">
            Start a session by sending a prompt.
          </p>
          <div
            v-for="(message, index) in messages"
            :key="index"
            class="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm"
            :class="message.role === 'user' ? 'ml-auto bg-stone-900 text-stone-50' : 'bg-stone-800 text-stone-50'"
          >
            <p v-if="message.role === 'user'">{{ message.text }}</p>
            <div v-else class="space-y-2">
              <div class="flex items-center justify-between text-[11px] uppercase tracking-[0.3em] text-stone-400">
                <span>Agent</span>
                <button
                  class="rounded-full border border-stone-700/80 bg-stone-900/80 p-1 text-stone-300 transition hover:border-stone-400"
                  @click="message.showDetails = !message.showDetails"
                  title="Toggle details"
                >
                  <Eye class="h-3 w-3" />
                </button>
              </div>
              <p v-if="message.header" class="text-xs text-stone-400" v-html="renderMarkdown(message.header)"></p>
              <div v-if="message.thinking" class="flex items-start gap-2 text-sm text-stone-200">
                <span
                  v-if="assistantIndex === index && sending"
                  class="inline-flex h-2 w-2 animate-pulse rounded-full bg-emerald-400"
                ></span>
                <span class="italic" v-html="renderMarkdown(message.thinking)"></span>
              </div>
              <p v-if="message.final" class="text-sm text-stone-100" v-html="renderMarkdown(message.final)"></p>
              <div
                v-if="message.showDetails"
                class="mt-2 rounded-2xl border border-stone-700/60 bg-stone-900/50 p-3 text-xs text-stone-200"
              >
                <div class="flex flex-wrap gap-2">
                  <button
                    class="rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.2em]"
                    :class="message.activeSection === 'header'
                      ? 'border-stone-400 bg-stone-800 text-stone-100'
                      : 'border-stone-600 text-stone-300'"
                    @click="message.activeSection = 'header'"
                  >
                    Header
                  </button>
                  <button
                    class="rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.2em]"
                    :class="message.activeSection === 'thinking'
                      ? 'border-stone-400 bg-stone-800 text-stone-100'
                      : 'border-stone-600 text-stone-300'"
                    @click="message.activeSection = 'thinking'"
                  >
                    Thinking
                  </button>
                  <button
                    class="rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.2em]"
                    :class="message.activeSection === 'final'
                      ? 'border-stone-400 bg-stone-800 text-stone-100'
                      : 'border-stone-600 text-stone-300'"
                    @click="message.activeSection = 'final'"
                  >
                    Final
                  </button>
                  <button
                    class="rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.2em]"
                    :class="message.activeSection === 'metadata'
                      ? 'border-stone-400 bg-stone-800 text-stone-100'
                      : 'border-stone-600 text-stone-300'"
                    @click="message.activeSection = 'metadata'"
                  >
                    Metadata
                  </button>
                </div>
                <div class="mt-2 rounded-lg bg-stone-950/50 p-2 text-stone-200">
                  <div
                    v-if="message.activeSection === 'header'"
                    class="message-markdown"
                    v-html="renderMarkdown(message.header || 'No header')"
                  ></div>
                  <div
                    v-else-if="message.activeSection === 'thinking'"
                    class="message-markdown"
                    v-html="renderMarkdown(message.thinking || 'No thinking')"
                  ></div>
                  <div
                    v-else-if="message.activeSection === 'final'"
                    class="message-markdown"
                    v-html="renderMarkdown(message.final || 'No final')"
                  ></div>
                  <div
                    v-else
                    class="message-markdown"
                    v-html="renderMarkdown(message.metadata || 'No metadata')"
                  ></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <Card v-else class="border-stone-800/60 bg-stone-900/70">
      <CardHeader class="flex flex-row items-center justify-between space-y-0 p-4">
        <CardTitle class="text-sm uppercase tracking-[0.3em] text-stone-400">Changes</CardTitle>
        <Button variant="outline" size="sm" @click="copyDiff" :disabled="!diff">
          Copy all
        </Button>
      </CardHeader>
      <CardContent class="space-y-3 p-4">
        <p v-if="!diffFileList.length" class="text-sm text-stone-500">No changes yet.</p>
        <details
          v-for="file in diffFileList"
          :key="file.id"
          class="rounded-2xl border border-stone-700/70 bg-stone-950/60"
        >
          <summary
            class="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-stone-200 [&::-webkit-details-marker]:hidden"
          >
            <div>
              <p class="text-sm text-stone-50">{{ file.path }}</p>
              <p class="text-xs text-stone-400">{{ file.hunks }} hunks</p>
            </div>
            <Button variant="ghost" size="icon" @click.stop="copyFile(file.patch)" :disabled="!file.patch">
              <Copy class="h-3 w-3" />
            </Button>
          </summary>
          <div class="border-t border-stone-800 bg-stone-900/80 px-4 py-3">
            <div class="diff2html" v-html="file.html"></div>
          </div>
        </details>
      </CardContent>
    </Card>

    <div class="fixed bottom-4 left-4 right-4 z-40 rounded-2xl border border-stone-800/70 bg-stone-900/80 p-3 shadow-xl backdrop-blur">
      <div class="flex items-end gap-2">
        <Textarea
          v-model="prompt"
          rows="2"
          class="min-h-[44px] flex-1 resize-none border border-stone-800 bg-stone-950/70 text-sm text-stone-50 placeholder-stone-500 focus:border-emerald-400"
          placeholder="Describe what you want the agent to do..."
          @keydown.enter.exact.prevent="start"
          @keydown.enter.shift.exact.stop
        />
        <Button variant="secondary" @click="start" :disabled="!canSend || sending">Send</Button>
      </div>
    </div>

    <p v-if="error" class="text-sm text-rose-400">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import {
  createSession,
  getDiff,
  getSession,
  openEventStream,
  renameSession,
  sendInput,
  startSession,
  stopSessionKeepalive,
  stopSession,
  type DiffFile,
  type EventEnvelope,
  type Session
} from "../api";
import { activeSessionId } from "../state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import * as Diff2Html from "diff2html";
import { Copy, Eye, Info } from "lucide-vue-next";

const session = ref<Session | null>(null);
type ChatMessage = {
  role: "user" | "assistant";
  text?: string;
  header?: string;
  thinking?: string;
  final?: string;
  metadata?: string;
  showDetails?: boolean;
  activeSection?: "header" | "thinking" | "final" | "metadata";
};

const messages = ref<ChatMessage[]>([]);
const diff = ref("");
const diffFiles = ref<
  { id: string; path: string; hunks: number; html: string; patch: string }[]
>([]);
const error = ref("");
const prompt = ref("");
const sending = ref(false);
const lastSeq = ref(0);
const viewMode = ref<"chat" | "diff">("chat");
const infoOpen = ref(false);
const renameValue = ref("");
const renaming = ref(false);
const renameMessage = ref("");
let closeStream: (() => void) | null = null;
let assistantIndex = -1;
let reconnectTimer: number | null = null;

const canStop = computed(() => session.value?.state === "RUNNING");
const canSend = computed(
  () => session.value?.state === "CREATED" || session.value?.state === "RUNNING"
);
const statusDot = computed(() => {
  switch (session.value?.state) {
    case "RUNNING":
      return "bg-emerald-500";
    case "STOPPING":
      return "bg-amber-500";
    case "ERROR":
      return "bg-red-500";
    case "STOPPED":
      return "bg-stone-400";
    default:
      return "bg-stone-300";
  }
});
const headerInfo = computed(() => parseCodexHeader(session.value?.codex_header || ""));

const buildDiffView = (diffText: string, files: DiffFile[]) => {
  const parsedFiles = Diff2Html.parse(diffText);
  const htmlByPath = new Map<string, string>();
  parsedFiles.forEach((file) => {
    const path = (file.newName || file.oldName || "unknown").replace(/^b\//, "");
    const html = Diff2Html.html([file], {
      inputFormat: "json",
      showFiles: false,
      matching: "lines",
      outputFormat: "line-by-line"
    });
    htmlByPath.set(path, html);
  });
  return files.map((file, index) => ({
    id: `${index}-${file.path}`,
    path: file.path,
    hunks: file.hunks,
    patch: file.patch,
    html:
      htmlByPath.get(file.path) ||
      Diff2Html.html(file.patch, {
        inputFormat: "diff",
        showFiles: false,
        matching: "lines",
        outputFormat: "line-by-line"
      })
  }));
};

const diffFileList = computed(() =>
  Array.isArray(diffFiles.value) ? diffFiles.value : []
);

const resetView = () => {
  messages.value = [];
  diff.value = "";
  error.value = "";
  prompt.value = "";
  assistantIndex = -1;
};

const ensureSession = async () => {
  error.value = "";
  if (!activeSessionId.value) {
    return;
  }
  try {
    session.value = await getSession(activeSessionId.value);
  } catch (err) {
    error.value = String(err);
  }
};

const openStream = async () => {
  if (!activeSessionId.value) {
    return;
  }
  if (closeStream) {
    closeStream();
    closeStream = null;
  }
  try {
    closeStream = await openEventStream(activeSessionId.value, onEvent, onError);
  } catch (err) {
    error.value = String(err);
  }
};

const refreshDiff = async () => {
  error.value = "";
  if (!activeSessionId.value) {
    return;
  }
  try {
    const fetched = await getDiff(activeSessionId.value);
    diff.value = fetched.diff || buildSampleDiff();
    const files = Array.isArray(fetched.files) ? fetched.files : parseRawDiff(diff.value);
    const rendered = buildDiffView(diff.value, files);
    diffFiles.value = Array.isArray(rendered) ? rendered : [];
  } catch (err) {
    error.value = String(err);
  }
};

const start = async () => {
  error.value = "";
  if (!activeSessionId.value) {
    return;
  }
  const value = prompt.value.trim();
  if (!value) {
    error.value = "Prompt required.";
    return;
  }
  sending.value = true;
  messages.value.push({ role: "user", text: value });
  messages.value.push({
    role: "assistant",
    header: session.value?.codex_header || "",
    thinking: "",
    final: "",
    metadata: "",
    showDetails: false,
    activeSection: "final"
  });
  assistantIndex = messages.value.length - 1;
  prompt.value = "";
  try {
    if (session.value?.state === "RUNNING") {
      session.value = await sendInput(activeSessionId.value, value);
    } else {
      session.value = await startSession(activeSessionId.value, value);
    }
  } catch (err) {
    error.value = String(err);
  } finally {
    sending.value = false;
  }
};

const stop = async () => {
  error.value = "";
  if (!activeSessionId.value) {
    return;
  }
  try {
    session.value = await stopSession(activeSessionId.value);
  } catch (err) {
    error.value = String(err);
  }
};

const onEvent = (event: EventEnvelope) => {
  const seq = Number((event as { seq?: number }).seq || 0);
  if (seq && seq <= lastSeq.value) {
    return;
  }
  if (seq) {
    lastSeq.value = seq;
  }
  if (event.type === "output") {
    const payload = event.data as { text?: string; kind?: string };
    const text = String(payload.text || "");
    const kind = payload.kind || "final";
    if (assistantIndex < 0 || !messages.value[assistantIndex]) {
      messages.value.push({
        role: "assistant",
        header: session.value?.codex_header || "",
        thinking: "",
        final: "",
        metadata: "",
        showDetails: false,
        activeSection: "final"
      });
      assistantIndex = messages.value.length - 1;
    }
    const message = messages.value[assistantIndex];
    if (message.role !== "assistant") {
      return;
    }
    if (kind === "step") {
      message.thinking = `${message.thinking || ""}${text}`;
    } else {
      message.final = `${message.final || ""}${text}`;
    }
  }
  if (event.type === "metadata") {
    const payload = event.data as { raw?: string; key?: string; value?: unknown };
    const raw = payload.raw || "";
    const rendered = raw
      ? `${raw}\n`
      : `${payload.key || "meta"}: ${JSON.stringify(payload.value)}\n`;
    if (assistantIndex >= 0 && messages.value[assistantIndex]?.role === "assistant") {
      const message = messages.value[assistantIndex];
      message.metadata = `${message.metadata || ""}${rendered}`;
    }
  }
  if (event.type === "heartbeat") {
    const payload = event.data as { elapsed_s?: number; done?: boolean };
    if (assistantIndex >= 0 && messages.value[assistantIndex]?.role === "assistant") {
      const message = messages.value[assistantIndex];
      const elapsed = Number(payload.elapsed_s || 0).toFixed(1);
      const status = payload.done ? "done" : "running";
      message.metadata = `${message.metadata || ""}heartbeat: ${elapsed}s (${status})\n`;
    }
  }
  if (event.type === "session_state") {
    if (session.value) {
      session.value.state = String((event.data as { state?: string }).state || "");
    }
  }
};

const onError = (err: unknown) => {
  const message = String(err);
  if (
    message.includes("input stream") ||
    message.includes("Failed to fetch") ||
    message.includes("NetworkError")
  ) {
    scheduleReconnect();
    return;
  }
  error.value = message;
};

const scheduleReconnect = () => {
  if (reconnectTimer || !activeSessionId.value) {
    return;
  }
  if (closeStream) {
    closeStream();
    closeStream = null;
  }
  reconnectTimer = window.setTimeout(async () => {
    reconnectTimer = null;
    if (!activeSessionId.value) {
      return;
    }
    try {
      closeStream = await openEventStream(activeSessionId.value, onEvent, onError);
    } catch (err) {
      onError(err);
    }
  }, 1000);
};

const stopOnUnload = () => {
  if (!activeSessionId.value) {
    return;
  }
  if (session.value?.state !== "RUNNING") {
    return;
  }
  stopSessionKeepalive(activeSessionId.value);
};

const toggleInfo = async () => {
  infoOpen.value = !infoOpen.value;
  if (!infoOpen.value || !activeSessionId.value) {
    return;
  }
  try {
    session.value = await getSession(activeSessionId.value);
    renameValue.value = session.value?.name || "";
  } catch (err) {
    error.value = String(err);
  }
};

const applyRename = async () => {
  if (!activeSessionId.value) {
    return;
  }
  if (!renameValue.value.trim()) {
    renameMessage.value = "Name cannot be empty.";
    return;
  }
  renaming.value = true;
  renameMessage.value = "";
  try {
    session.value = await renameSession(activeSessionId.value, renameValue.value);
    renameMessage.value = "Updated";
  } catch (err) {
    renameMessage.value = String(err);
  } finally {
    renaming.value = false;
  }
};

const copyDiff = async () => {
  if (!diff.value) {
    return;
  }
  try {
    await navigator.clipboard.writeText(diff.value);
  } catch (err) {
    error.value = String(err);
  }
};

const copyFile = async (patch: string) => {
  if (!patch) {
    return;
  }
  try {
    await navigator.clipboard.writeText(patch);
  } catch (err) {
    error.value = String(err);
  }
};

const buildSampleDiff = () => `diff --git a/ui/src/views/ActiveSession.vue b/ui/src/views/ActiveSession.vue
index 2bce3a1..d93c7c0 100644
--- a/ui/src/views/ActiveSession.vue
+++ b/ui/src/views/ActiveSession.vue
@@ -3,7 +3,11 @@
-    <h2>Active Session</h2>
-    <p v-if=\\"session\\">State: {{ session.state }}</p>
+    <h2>
+      <span class=\\"status\\"></span>
+      Active Session
+    </h2>
+    <p v-if=\\"session\\">{{ session.repo_display }} · {{ session.state }}</p>
   </div>
@@ -42,6 +46,10 @@
-<pre class=\\"diff\\">{{ diff }}</pre>
+<div class=\\"diff-header\\">
+  <h3>Diff preview</h3>
+  <button>Copy</button>
+</div>
+<pre class=\\"diff\\"><code>{{ diff }}</code></pre>
diff --git a/ui/src/App.vue b/ui/src/App.vue
index f5a12c3..bd901fe 100644
--- a/ui/src/App.vue
+++ b/ui/src/App.vue
@@ -1,6 +1,9 @@
 <header class=\\"topbar\\">
-  <h1>Tether</h1>
+  <h1>
+    <span class=\\"brand-dot\\"></span>
+    Tether
+  </h1>
 </header>
@@ -72,6 +75,8 @@
-.topbar { background: #121312; }
+.topbar { background: #121312; }
+.brand-dot { width: 8px; height: 8px; border-radius: 50%; }
diff --git a/ui/src/views/Sessions.vue b/ui/src/views/Sessions.vue
index 9b1bc4a..f63ce2a 100644
--- a/ui/src/views/Sessions.vue
+++ b/ui/src/views/Sessions.vue
@@ -18,7 +18,10 @@
-  <button @click=\\"create\\">Create & open</button>
+  <button @click=\\"create\\">Create & open</button>
+  <button class=\\"ghost\\" @click=\\"refresh\\">Refresh</button>
@@ -80,6 +83,8 @@
-.session-card { display: flex; }
+.session-card { display: flex; }
+.session-card.active { border-color: var(--accent); }
`;

const parseRawDiff = (source: string): DiffFile[] => {
  const lines = source.split("\n");
  const files: { path: string; hunks: number; lines: string[] }[] = [];
  let current: { path: string; hunks: number; lines: string[] } | null = null;
  for (const line of lines) {
    if (line.startsWith("diff --git ")) {
      if (current) {
        files.push(current);
      }
      const match = line.match(/diff --git a\/(.+?) b\/(.+)/);
      const path = match ? match[2] : "unknown";
      current = { path, hunks: 0, lines: [line] };
      continue;
    }
    if (!current) {
      current = { path: "unknown", hunks: 0, lines: [] };
    }
    if (line.startsWith("@@")) {
      current.hunks += 1;
    }
    current.lines.push(line);
  }
  if (current) {
    files.push(current);
  }
  return files.map((file) => ({
    path: file.path,
    hunks: file.hunks,
    patch: file.lines.join("\n")
  }));
};

const parseCodexHeader = (raw: string): {
  version: string;
  model: string;
  provider: string;
  approval: string;
  sandbox: string;
  sessionId: string;
} | null => {
  if (!raw) {
    return null;
  }
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && line !== "--------");
  const versionLine = lines.find((line) => line.startsWith("OpenAI Codex")) || "";
  const getValue = (key: string) => {
    const line = lines.find((item) => item.toLowerCase().startsWith(`${key}:`));
    return line ? line.split(":").slice(1).join(":").trim() : "unknown";
  };
  return {
    version: versionLine || "unknown",
    model: getValue("model"),
    provider: getValue("provider"),
    approval: getValue("approval"),
    sandbox: getValue("sandbox"),
    sessionId: getValue("session id")
  };
};

const renderMarkdown = (source: string): string => {
  const escaped = source
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const lines = escaped.split("\n").map((line) => {
    const trimmed = line.trim();
    if (trimmed.toLowerCase() === "thinking") {
      return "<em>thinking</em>";
    }
    let out = line.replace(/`([^`]+)`/g, "<code>$1</code>");
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|\s)\*([^*]+)\*/g, "$1<em>$2</em>");
    return out;
  });
  return lines.join("<br />");
};

watch(viewMode, async (mode) => {
  if (mode === "diff") {
    await refreshDiff();
  }
});

watch(activeSessionId, async (newId, oldId) => {
  if (newId === oldId) {
    return;
  }
  resetView();
  session.value = null;
  if (closeStream) {
    closeStream();
    closeStream = null;
  }
  if (!newId) {
    return;
  }
  await ensureSession();
  await openStream();
});

onMounted(async () => {
  if (activeSessionId.value) {
    await ensureSession();
    await openStream();
  }
  window.addEventListener("beforeunload", stopOnUnload);
  window.addEventListener("pagehide", stopOnUnload);
});

onUnmounted(() => {
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  window.removeEventListener("beforeunload", stopOnUnload);
  window.removeEventListener("pagehide", stopOnUnload);
  if (closeStream) {
    closeStream();
  }
});
</script>
