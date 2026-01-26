import { ref, watch, onUnmounted } from "vue";
import { checkDirectory, type DirectoryCheck } from "@/api";

export function useDirectoryCheck(debounceMs = 400) {
  const input = ref("");
  const checking = ref(false);
  const probe = ref<DirectoryCheck | null>(null);
  const error = ref("");

  let timer: number | null = null;

  const clear = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const check = async (path: string): Promise<DirectoryCheck | null> => {
    clear();
    const trimmed = path.trim();
    if (!trimmed) {
      probe.value = null;
      error.value = "";
      checking.value = false;
      return null;
    }

    checking.value = true;
    try {
      const status = await checkDirectory(trimmed);
      probe.value = status;
      error.value = status.exists ? "" : "Directory not found";
      return status;
    } catch (err) {
      probe.value = null;
      error.value = String(err);
      return null;
    } finally {
      checking.value = false;
    }
  };

  const scheduleCheck = (value: string) => {
    clear();
    const trimmed = value.trim();
    if (!trimmed) {
      probe.value = null;
      error.value = "";
      checking.value = false;
      return;
    }
    checking.value = true;
    timer = setTimeout(async () => {
      await check(trimmed);
      timer = null;
    }, debounceMs) as unknown as number;
  };

  // Auto-check when input changes
  watch(input, (value) => {
    scheduleCheck(value);
  });

  onUnmounted(clear);

  return {
    input,
    checking,
    probe,
    error,
    check,
    clear
  };
}
