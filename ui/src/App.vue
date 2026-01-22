<template>
  <div class="min-h-screen bg-stone-950 text-stone-50">
    <header class="sticky top-0 z-10 border-b border-stone-800/60 bg-stone-950/90 backdrop-blur">
      <div class="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <div class="flex items-center gap-3">
          <Button variant="ghost" size="icon" class="h-9 w-9 text-stone-50" @click="drawerOpen = true">
            <Menu class="h-5 w-5" />
          </Button>
          <div>
            <p class="text-base font-semibold tracking-wide">Tether</p>
            <p class="text-[10px] uppercase tracking-[0.3em] text-stone-400">Local agent console</p>
          </div>
        </div>
        <input
          ref="directoryFileInput"
          type="file"
          webkitdirectory
          mozdirectory
          directory
          multiple
          class="hidden"
          @change="onDirectoryFileSelected"
        />
        <div class="flex items-center gap-2">
          <Button size="sm" variant="secondary" @click="createTempSession" :disabled="creating">
            New session
          </Button>
          <Button size="sm" variant="destructive" @click="removeActive" :disabled="deleteDisabled">
            Delete
          </Button>
        </div>
      </div>
    </header>

    <main class="mx-auto w-full max-w-5xl px-4 pb-24 pt-4">
      <RouterView />
    </main>

    <Sheet :open="drawerOpen" @update:open="drawerOpen = $event">
      <SheetContent side="left" class="w-full max-w-xs border-stone-800 bg-stone-950 text-stone-50">
        <SheetHeader>
          <SheetTitle class="text-stone-50">Sessions</SheetTitle>
          <SheetDescription class="text-sm text-stone-400">Grouped by directory.</SheetDescription>
        </SheetHeader>
        <div class="px-3">
          <Button
            size="sm"
            variant="outline"
            class="w-full"
            @click="createPanelOpen = !createPanelOpen"
          >
            {{ createPanelOpen ? "Hide start options" : "Start a new session" }}
          </Button>
          <transition name="fade">
            <div
              v-if="createPanelOpen"
              class="mt-3 space-y-3 rounded-2xl border border-stone-800/60 bg-stone-900/60 p-3"
            >
              <div class="flex items-center gap-2 text-sm text-stone-300">
                <Folder class="h-4 w-4" />
                <p class="text-xs uppercase tracking-[0.2em]">Start from an existing directory</p>
              </div>
              <Input v-model="directoryInput" size="sm" placeholder="/path/to/project" />
              <div class="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  :disabled="checkingDirectory || !directoryInput.trim()"
                  @click="createDirectorySession"
                >
                  Use directory
                </Button>
                <Button size="sm" variant="ghost" @click="openDirectoryPicker">
                  Pick directory
                </Button>
                <Button size="sm" variant="ghost" @click="createTempSession" :disabled="creating">
                  New temp workspace
                </Button>
              </div>
              <p class="text-[11px] text-stone-400">
                <span v-if="checkingDirectory">Checking directory…</span>
                <span v-else-if="directoryProbe">
                  <span v-if="directoryProbe.exists">
                    <span v-if="directoryProbe.is_git">Git repo detected.</span>
                    <span v-else>No git repository detected.</span>
                  </span>
                  <span v-else>Directory unavailable.</span>
                </span>
                <span v-else>Provide a path to see status.</span>
              </p>
              <p v-if="directoryError" class="text-[11px] text-rose-400">{{ directoryError }}</p>
            </div>
          </transition>
        </div>
        <div class="space-y-3 px-3 pb-4">
          <div
            v-for="group in directoryGroups"
            :key="group.key"
            class="rounded-2xl border border-stone-800/60 bg-stone-900/70 p-3"
            :title="group.path || 'Temporary workspace'"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-stone-50">{{ group.label }}</p>
                <p class="text-xs text-stone-400">{{ group.path || "Temporary workspace" }}</p>
              </div>
              <Badge variant="outline" class="text-[10px] uppercase tracking-[0.2em]">
                {{ group.hasGit ? "Git repo" : "No git" }}
              </Badge>
            </div>
            <ul class="mt-3 space-y-2">
              <li v-for="session in group.sessions" :key="session.id">
                <button
                  class="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition hover:bg-stone-800/80"
                  :class="{
                    'border border-emerald-400/60 bg-emerald-500/10 text-emerald-200': session.id === activeSessionId
                  }"
                  @click="selectSession(session.id)"
                >
                  <div class="space-y-0.5">
                    <p class="font-semibold">{{ session.name || session.repo_display }}</p>
                    <p class="text-[10px] uppercase tracking-[0.3em] text-stone-400">{{ session.state }}</p>
                  </div>
                  <span class="text-[10px] text-stone-400">{{ session.id.slice(-6) }}</span>
                </button>
              </li>
            </ul>
          </div>
          <p v-if="!directoryGroups.length" class="text-xs text-stone-500">No sessions yet.</p>
        </div>
      </SheetContent>
    </Sheet>

    <transition name="fade">
      <div
        v-if="showOnboarding"
        class="fixed inset-0 z-40 flex items-center justify-center bg-stone-950/80 px-4"
      >
        <Card class="w-full max-w-md space-y-4 border border-stone-800/80 bg-stone-900/80">
          <CardContent class="space-y-4">
            <div class="space-y-2">
              <p class="text-lg font-semibold text-stone-50">Start your first agent</p>
              <p class="text-sm text-stone-400">
                Pick a directory to work in or spin up a disposable workspace.
              </p>
            </div>
          <div class="space-y-2">
            <Button class="w-full" variant="outline" @click="createTempSession" :disabled="creating">
              Create temporary workspace
            </Button>
            <div class="flex flex-col gap-2">
              <Input v-model="directoryInput" size="sm" placeholder="/path/to/project" />
              <Button class="w-full" variant="ghost" @click="openDirectoryPicker">
                Pick directory
              </Button>
              <Button
                class="w-full"
                @click="createDirectorySession"
                  :disabled="!directoryProbe?.exists || checkingDirectory || creating"
                >
                  Use directory
                </Button>
              </div>
              <p v-if="directoryError" class="text-[11px] text-rose-400">{{ directoryError }}</p>
              <p v-else class="text-[11px] text-stone-400">
                Git status:
                <span v-if="directoryProbe">
                  {{ directoryProbe.is_git ? "Git repo" : "No git repo" }}
                </span>
                <span v-else>Awaiting input</span>.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </transition>

    <p
      v-if="error"
      class="fixed bottom-4 left-4 right-4 rounded-2xl border border-rose-500/70 bg-rose-500/10 px-4 py-2 text-sm text-rose-200"
    >
      {{ error }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterView } from "vue-router";
import { Folder, Menu } from "lucide-vue-next";
import {
  createSession,
  deleteSession,
  listSessions,
  checkDirectory,
  type DirectoryCheck,
  type Session
} from "./api";
import { activeSessionId } from "./state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";

const drawerOpen = ref(false);
const sessions = ref<Session[]>([]);
const creating = ref(false);
const deleting = ref(false);
const error = ref("");
const loaded = ref(false);
const directoryInput = ref("");
const checkingDirectory = ref(false);
const directoryProbe = ref<DirectoryCheck | null>(null);
const directoryError = ref("");
const createPanelOpen = ref(false);
const directoryFileInput = ref<HTMLInputElement | null>(null);
let directoryTimer: number | null = null;

const activeSession = computed(() =>
  sessions.value.find((session) => session.id === activeSessionId.value)
);

const deleteDisabled = computed(() => {
  if (!activeSessionId.value || deleting.value) {
    return true;
  }
  const state = activeSession.value?.state;
  return state === "RUNNING" || state === "STOPPING";
});

const showOnboarding = computed(
  () => loaded.value && !sessions.value.length && !creating.value
);

const maybeSelectDefaultSession = (list: Session[]) => {
  if (!activeSessionId.value && list.length) {
    activeSessionId.value = list[0].id;
  }
};

const openDirectoryPicker = () => {
  directoryError.value = "";
  directoryFileInput.value?.click();
};

const onDirectoryFileSelected = (event: Event) => {
  const input = event.target as HTMLInputElement;
  const files = input.files;
  if (!files?.length) {
    return;
  }
  const file = files[0] as File & { path?: string; mozFullPath?: string; webkitRelativePath?: string };
  const candidate =
    file.path ||
    (file as { mozFullPath?: string }).mozFullPath ||
    (file.webkitRelativePath ? file.webkitRelativePath.split("/")[0] : "");
  if (!candidate) {
    directoryError.value = "Could not resolve directory from selection";
    input.value = "";
    return;
  }
  directoryInput.value = candidate;
  scheduleDirectoryCheck(candidate);
  input.value = "";
};

const formatDirectoryLabel = (dir: string | null) => {
  if (!dir) {
    return "Temporary workspace";
  }
  const trimmed = dir.replace(/[\\/]+$/, "");
  const segments = trimmed.split(/[\\/]/).filter(Boolean);
  return segments.at(-1) || trimmed;
};

const directoryGroups = computed(() => {
  const map = new Map<string, { key: string; label: string; path: string | null; sessions: Session[]; hasGit: boolean }>();
  sessions.value.forEach((session) => {
    const key = session.directory ?? session.repo_display ?? `temp-${session.id}`;
    if (!map.has(key)) {
      map.set(key, {
        key,
        label: formatDirectoryLabel(session.directory),
        path: session.directory,
        sessions: [],
        hasGit: Boolean(session.directory_has_git)
      });
    }
    const group = map.get(key)!;
    group.sessions.push(session);
    if (session.directory_has_git) {
      group.hasGit = true;
    }
  });
  return Array.from(map.values());
});

const refreshSessions = async () => {
  error.value = "";
  try {
    const fetched = await listSessions();
    sessions.value = fetched;
    maybeSelectDefaultSession(fetched);
  } catch (err) {
    error.value = String(err);
  } finally {
    loaded.value = true;
  }
};

const createTempSession = async () => {
  creating.value = true;
  error.value = "";
  try {
    const created = await createSession({ repoId: "repo_local" });
    activeSessionId.value = created.id;
    await refreshSessions();
    drawerOpen.value = false;
    createPanelOpen.value = false;
  } catch (err) {
    error.value = String(err);
  } finally {
    creating.value = false;
  }
};

const createDirectorySession = async () => {
  const path = directoryInput.value.trim();
  if (!path) {
    directoryError.value = "Provide a directory";
    return;
  }
  let status = directoryProbe.value;
  if (!status || status.path !== path) {
    checkingDirectory.value = true;
    try {
      status = await checkDirectory(path);
      directoryProbe.value = status;
    } catch (err) {
      directoryError.value = String(err);
      checkingDirectory.value = false;
      return;
    } finally {
      checkingDirectory.value = false;
    }
  }
  if (!status.exists) {
    directoryError.value = "Directory not found";
    return;
  }
  creating.value = true;
  error.value = "";
    try {
      const created = await createSession({ directory: path });
      activeSessionId.value = created.id;
      await refreshSessions();
      directoryError.value = "";
      drawerOpen.value = false;
      createPanelOpen.value = false;
    } catch (err) {
    error.value = String(err);
  } finally {
    creating.value = false;
  }
};

const selectSession = (id: string) => {
  activeSessionId.value = id;
  drawerOpen.value = false;
};

const removeActive = async () => {
  if (!activeSessionId.value) {
    return;
  }
  deleting.value = true;
  error.value = "";
  try {
    await deleteSession(activeSessionId.value);
    activeSessionId.value = null;
    await refreshSessions();
  } catch (err) {
    error.value = String(err);
  } finally {
    deleting.value = false;
  }
};

const scheduleDirectoryCheck = (value: string) => {
  if (directoryTimer) {
    window.clearTimeout(directoryTimer);
  }
  const trimmed = value.trim();
  if (!trimmed) {
    directoryProbe.value = null;
    directoryError.value = "";
    checkingDirectory.value = false;
    return;
  }
  checkingDirectory.value = true;
  directoryTimer = window.setTimeout(async () => {
    try {
      const status = await checkDirectory(trimmed);
      directoryProbe.value = status;
      if (!status.exists) {
        directoryError.value = "Directory not found";
      } else {
        directoryError.value = "";
      }
    } catch (err) {
      directoryProbe.value = null;
      directoryError.value = String(err);
    } finally {
      checkingDirectory.value = false;
      directoryTimer = null;
    }
  }, 400);
};

watch(directoryInput, (value) => {
  scheduleDirectoryCheck(value);
});

watch(drawerOpen, (open) => {
  if (open) {
    refreshSessions().catch(() => undefined);
  }
});

watch(activeSessionId, (newId, oldId) => {
  if (newId === oldId) {
    return;
  }
  refreshSessions().catch(() => undefined);
});

onMounted(refreshSessions);

onUnmounted(() => {
  if (directoryTimer) {
    window.clearTimeout(directoryTimer);
  }
});
</script>
