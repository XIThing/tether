export function formatState(state: string | undefined): string {
  if (!state) return "";
  const labels: Record<string, string> = {
    CREATED: "Ready",
    RUNNING: "Running",
    AWAITING_INPUT: "Awaiting input",
    INTERRUPTING: "Interrupting",
    ERROR: "Error"
  };
  return labels[state] || state.toLowerCase().replace(/_/g, " ");
}

export function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export function formatSessionId(id: string): string {
  return id.slice(0, 8);
}

export function getStatusDotClass(state: string | undefined): string {
  switch (state) {
    case "RUNNING":
      return "bg-emerald-500";
    case "AWAITING_INPUT":
      return "bg-amber-400 animate-pulse";
    case "INTERRUPTING":
      return "bg-amber-500";
    case "ERROR":
      return "bg-rose-500";
    case "CREATED":
      return "bg-blue-400";
    default:
      return "";
  }
}
