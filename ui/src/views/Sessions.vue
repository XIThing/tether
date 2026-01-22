<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h2>Sessions</h2>
        <p class="muted">Pick a session to make it active.</p>
      </div>
      <div class="header-actions">
        <button class="ghost" @click="refresh">Refresh</button>
        <RouterLink class="ghost link" to="/settings">Settings</RouterLink>
      </div>
    </header>

    <div class="create">
      <input v-model="repoId" placeholder="Repo id or path" />
      <button @click="create">Create & open</button>
    </div>

    <ul class="session-list">
      <li
        v-for="session in sessions"
        :key="session.id"
        :class="{ active: session.id === activeSessionId }"
      >
        <div class="session-card">
          <div class="session-meta">
            <strong>{{ session.id }}</strong>
            <span class="state">{{ session.state }}</span>
          </div>
          <div class="session-meta">
            <small>{{ session.last_activity_at }}</small>
            <small>{{ session.repo_display }}</small>
          </div>
          <div class="session-actions">
            <button class="ghost" @click="selectSession(session.id)">Open</button>
            <button
              class="danger"
              @click="removeSession(session.id)"
              :disabled="session.state === 'RUNNING' || session.state === 'STOPPING'"
            >
              Delete
            </button>
          </div>
        </div>
      </li>
    </ul>

    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { createSession, deleteSession, listSessions, type Session } from "../api";
import { activeSessionId } from "../state";

const sessions = ref<Session[]>([]);
const repoId = ref("repo_local");
const error = ref("");
const router = useRouter();

const refresh = async () => {
  error.value = "";
  try {
    sessions.value = await listSessions();
  } catch (err) {
    error.value = String(err);
  }
};

const create = async () => {
  error.value = "";
  try {
    const created = await createSession(repoId.value);
    activeSessionId.value = created.id;
    await refresh();
    await router.push("/");
  } catch (err) {
    error.value = String(err);
  }
};

const selectSession = async (id: string) => {
  activeSessionId.value = id;
  await router.push("/");
};

const removeSession = async (id: string) => {
  error.value = "";
  try {
    await deleteSession(id);
    if (activeSessionId.value === id) {
      activeSessionId.value = null;
    }
    await refresh();
  } catch (err) {
    error.value = String(err);
  }
};

onMounted(refresh);
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.page-header p {
  margin: 4px 0 0;
}

.muted {
  color: var(--muted);
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.create {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.create input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
}

.create button {
  width: 100%;
}

.session-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.session-list li {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  animation: fade-in 240ms ease-out;
}

.session-list li.active {
  border-color: var(--accent);
  box-shadow: 0 12px 26px -20px rgba(212, 106, 31, 0.7);
}

.session-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.session-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.state {
  font-weight: 600;
  color: var(--muted);
}

.session-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.error {
  color: #9b1c1c;
}

button {
  padding: 10px 14px;
  border: none;
  background: var(--accent);
  color: #1b1c18;
  border-radius: 999px;
  font-weight: 600;
}

.ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--ink);
}

.danger {
  background: #f2c1b5;
  color: #4a1712;
}

.link {
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}

@media (min-width: 640px) {
  .create {
    flex-direction: row;
  }

  .create button {
    width: auto;
    flex: 0 0 auto;
  }
}
</style>
