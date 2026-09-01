const LIVE_STATES = new Set(["live", "starting"]);

export function canStart({ previewOk, rtmpUrl, rtmpKey, ack, state }) {
  const destOk = Boolean(String(rtmpUrl ?? "").trim() && String(rtmpKey ?? ""));
  return Boolean(previewOk && destOk && ack && !LIVE_STATES.has(state));
}

export function canStop({ state }) {
  return state === "live";
}

export function pillFor({ previewOk, state }) {
  if (state === "live") return "live";
  if (state === "error") return "error";
  if (state === "stopped") return "stopped";
  if (state === "starting") return "preview";
  if (previewOk) return "preview";
  return "idle";
}

export function pillLabel(status) {
  switch (status) {
    case "preview":
      return "Preview";
    case "live":
      return "LIVE";
    case "stopped":
      return "Stopped";
    case "error":
      return "Error";
    default:
      return "Idle";
  }
}
