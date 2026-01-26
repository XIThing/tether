import { ref, onMounted, onUnmounted } from "vue";
import { AUTH_REQUIRED_EVENT, getToken, setToken } from "@/api";

// Shared state
const authRequired = ref(false);
const modalOpen = ref(false);
const tokenInput = ref(getToken());
const tokenSaved = ref(false);

export function useAuth() {
  const handleAuthRequired = () => {
    authRequired.value = true;
    tokenInput.value = getToken();
    modalOpen.value = true;
  };

  const saveToken = (onSuccess?: () => void) => {
    setToken(tokenInput.value.trim());
    tokenSaved.value = true;
    setTimeout(() => {
      tokenSaved.value = false;
    }, 1200);
    modalOpen.value = false;
    authRequired.value = false;
    onSuccess?.();
  };

  const openModal = () => {
    tokenInput.value = getToken();
    modalOpen.value = true;
  };

  const closeModal = () => {
    modalOpen.value = false;
  };

  // Listen for auth required events
  onMounted(() => {
    window.addEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
  });

  onUnmounted(() => {
    window.removeEventListener(AUTH_REQUIRED_EVENT, handleAuthRequired);
  });

  return {
    authRequired,
    modalOpen,
    tokenInput,
    tokenSaved,
    saveToken,
    openModal,
    closeModal
  };
}
