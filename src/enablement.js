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

export function canContinue({ previewOk, configured, ack, selectedKeyId }) {
  const dest = selectedKeyId != null ? Boolean(selectedKeyId) : Boolean(configured);
  return Boolean(previewOk && dest && ack);
}

export function canStart({ previewOk, configured, ack, state, selectedKeyId, selectedBusy }) {
  const destOk = canContinue({ previewOk, configured, ack, selectedKeyId });
  if (selectedBusy) return false;
  if (selectedKeyId) return destOk;
  return Boolean(destOk && !LIVE_STATES.has(state));
}

export function canStop({ state }) {
  return state === "live" || state === "error";
}

/**
 * Next chrome after start/stop/status.
 * Status polls must not clear a real Error (idle+null loopback wipe).
 * Operator Stop (source "command") may leave Error.
 */
export function nextChrome({ backend, error }, result, source) {
  const currentError = typeof error === "string" ? error : "";
  if (source === "status") {
    if (!isUsableStatus(result)) {
      return { backend, error: currentError };
    }
    if (backend === "error" && backendFromResult(result) !== "error") {
      return { backend: "error", error: currentError };
    }
  }
  if (!result) {
    return { backend: "error", error: currentError };
  }
  return {
    backend: backendFromResult(result),
    error: typeof result.error === "string" ? result.error : "",
  };
}

export function pillFor({ previewOk, state }) {
  if (state === "live") return "live";
  if (state === "error") return "error";
  if (state === "stopped") return "stopped";
  if (state === "starting") return "starting";
  if (previewOk) return "preview";
  return "idle";
}

export function pillLabel(status) {
  switch (status) {
    case "preview":
      return "Preview";
    case "starting":
      return "Starting";
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

/**
 * Transport helper copy. On Error, show the API error string as-is
 * (caller redacts rtmp secrets only — never rewrite NotLiveError text).
 */
export function transportHelper({ backend, error }) {
  if (backend === "live") return "Retransmitting live to X";
  if (backend === "error" && nonEmptyError(error)) return error;
  return "Idle until ready";
}
