const LIVE_STATES = new Set(["live", "starting"]);

function nonEmptyError(error) {
  return typeof error === "string" && error.trim() !== "";
}

/**
 * Real GET /api/live/status session payload only.
 * Network / proxy 502 / non-OK failures are not usable — chrome stays as-is (Idle).
 */
export function isUsableStatus(result) {
  return Boolean(result && result.httpStatus === 200);
}

/** Map start/stop/status result → operator backend state for the status pill. */
export function backendFromResult(result) {
  if (!result) return "error";
  if (result.httpStatus === 400 || nonEmptyError(result.error) || result.state === "error") {
    return "error";
  }
  return typeof result.state === "string" && result.state ? result.state : "error";
}

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
