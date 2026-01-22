<template>
  <section class="space-y-4">
    <Card class="border-stone-200">
      <CardHeader>
        <CardTitle class="text-sm uppercase tracking-[0.3em] text-stone-500">Settings</CardTitle>
      </CardHeader>
      <CardContent class="space-y-4">
        <label class="space-y-2 text-sm font-medium text-stone-700">
          Base URL
          <Input v-model="baseUrl" placeholder="http://localhost:8787" />
        </label>
        <label class="space-y-2 text-sm font-medium text-stone-700">
          Token
          <Input v-model="token" placeholder="AGENT_TOKEN" />
        </label>
        <div class="flex items-center gap-3">
          <Button @click="save">Save</Button>
          <span v-if="saved" class="text-sm text-emerald-600">Saved.</span>
        </div>
      </CardContent>
    </Card>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { getBaseUrl, getToken, setBaseUrl, setToken } from "../api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const baseUrl = ref(getBaseUrl());
const token = ref(getToken());
const saved = ref(false);

const save = () => {
  setBaseUrl(baseUrl.value.trim());
  setToken(token.value.trim());
  saved.value = true;
  setTimeout(() => {
    saved.value = false;
  }, 1200);
};
</script>
