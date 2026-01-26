<template>
  <div class="min-h-screen bg-stone-950 text-stone-50">
    <div :class="settingsOpen ? 'pointer-events-none' : ''">
      <AppHeader
        :active-session="activeSession"
        :has-active-session="!!activeSessionId"
        :syncing="syncing"
        :status-dot="statusDot"
        @open-drawer="drawerOpen = true"
        @sync="handleSync"
        @rename="openRename"
        @info="openInfo"
      />

      <main class="mx-auto w-full max-w-3xl px-4 pb-32 pt-4">
        <RouterView />
      </main>

      <SessionDrawer
        v-model:open="drawerOpen"
        v-model:directory-input="directoryInput"
        :sessions="sessions"
        :active-session-id="activeSessionId"
        :creating="creating"
        :deleting="deleting"
        :checking-directory="checkingDirectory"
        :directory-probe="directoryProbe"
        :directory-error="directoryError"
        @select="handleSessionSelect"
        @delete="removeSession"
        @create="createDirectorySession"
        @attach="openExternalBrowser"
        @add-to-directory="addSessionToDirectory"
        @settings="openSettings"
      />

      <ExternalSessionBrowser
        :open="externalBrowserOpen"
        @update:open="externalBrowserOpen = $event"
        @attached="handleSessionAttached"
      />
    </div>

    <!-- Settings dialog -->
    <Dialog :open="settingsOpen" @update:open="settingsOpen = $event">
      <DialogContent class="max-w-md border-stone-800 bg-stone-900">
        <DialogHeader>
          <DialogTitle class="text-stone-100">Settings</DialogTitle>
        </DialogHeader>
        <Settings />
      </DialogContent>
    </Dialog>

    <!-- Auth dialog -->
    <Dialog :open="authModalOpen" @update:open="authModalOpen = $event">
      <DialogContent class="max-w-sm border-stone-800 bg-stone-900">
        <DialogHeader>
          <DialogTitle class="text-stone-100">Welcome to Tether</DialogTitle>
        </DialogHeader>
        <div class="space-y-4">
          <p class="text-sm text-stone-400">
            Enter the token from your agent server to get started.
          </p>
          <Input
            v-model="tokenInput"
            type="password"
            placeholder="Token"
            class="border-stone-700 bg-stone-800"
          />
          <button
            class="w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-500"
            @click="saveToken"
          >
            {{ tokenSaved ? 'Connected!' : 'Connect' }}
          </button>
        </div>
      </DialogContent>
    </Dialog>

    <!-- Onboarding -->
    <OnboardingOverlay
      :visible="showOnboarding"
      :directory-input="directoryInput"
      :checking="checkingDirectory"
      :probe="directoryProbe"
      :error="directoryError"
      :creating="creating"
      @update:directory-input="directoryInput = $event"
      @attach="openExternalBrowser"
      @create="createDirectorySession"
    />

    <!-- Connection error -->
    <ConnectionErrorOverlay
      :visible="isConnectionError && !sessions.length"
      @retry="refreshSessions"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { RouterView } from "vue-router";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import Settings from "./views/Settings.vue";
import ExternalSessionBrowser from "@/components/external/ExternalSessionBrowser.vue";
import {
  AppHeader,
  SessionDrawer,
  OnboardingOverlay,
  ConnectionErrorOverlay
} from "@/components/layout";
import { requestInfo, requestRename } from "./state";
import {
  useSessions,
  useDirectoryCheck,
  useAuth,
  getStatusDotClass
} from "@/composables";

// Core session state
const {
  sessions,
  activeSessionId,
  activeSession,
  loaded,
  error,
  creating,
  deleting,
  syncing,
  isConnectionError,
  refresh: refreshSessions,
  create: createSession,
  remove: removeSession,
  select: selectSession,
  sync: handleSync
} = useSessions();

// Directory input validation
const {
  input: directoryInput,
  checking: checkingDirectory,
  probe: directoryProbe,
  error: directoryError
} = useDirectoryCheck();

// Auth modal
const {
  authRequired,
  modalOpen: authModalOpen,
  tokenInput,
  tokenSaved,
  saveToken: handleSaveToken
} = useAuth();

// Local UI state
import { ref } from "vue";
const drawerOpen = ref(false);
const settingsOpen = ref(false);
const externalBrowserOpen = ref(false);

// Computed
const statusDot = computed(() => getStatusDotClass(activeSession.value?.state));

const showOnboarding = computed(
  () => loaded.value && !sessions.value.length && !creating.value && !authRequired.value && !error.value
);

// Actions
const openSettings = () => { settingsOpen.value = true; };
const openExternalBrowser = () => { externalBrowserOpen.value = true; };

const openRename = () => {
  if (!activeSessionId.value) return;
  requestRename.value += 1;
};

const openInfo = () => {
  if (!activeSessionId.value) return;
  requestInfo.value += 1;
};

const saveToken = () => {
  handleSaveToken(() => refreshSessions());
};

const handleSessionSelect = (id: string) => {
  selectSession(id);
  drawerOpen.value = false;
};

const handleSessionAttached = async (sessionId: string) => {
  await refreshSessions();
  selectSession(sessionId);
  drawerOpen.value = false;
};

const createDirectorySession = async () => {
  const path = directoryInput.value.trim();
  if (!path || !directoryProbe.value?.exists) return;
  const created = await createSession(path);
  if (created) {
    drawerOpen.value = false;
  }
};

const addSessionToDirectory = async (path: string) => {
  await createSession(path);
};

// Watchers
watch(drawerOpen, (open) => {
  if (open) refreshSessions();
});

watch(activeSessionId, (newId, oldId) => {
  if (newId === oldId) return;
  refreshSessions();
  if (newId) handleSync();
});

// Lifecycle
onMounted(() => {
  refreshSessions();
});
</script>

