import "./style.css";
import { parseSourceUrl } from "./sourceUrl.js";
import {
  backendFromResult,
  canContinue,
  canStart,
  canStop,
  isUsableStatus,
  pillFor,
  pillLabel,
  transportHelper,
} from "./enablement.js";
import { retransApi } from "./retransApi.js";

const SIGNIN_HELPER = "Save Media Studio RTMP once. Not X OAuth.";

const els = {
  beat1: document.getElementById("beat-1"),
  beat2: document.getElementById("beat-2"),
  beat3: document.getElementById("beat-3"),
  source: document.getElementById("source_url"),
  previewBtn: document.getElementById("preview-btn"),
  pasteHelper: document.getElementById("paste-helper"),
  previewCards: document.querySelectorAll("[data-preview]"),
  rtmpUrl: document.getElementById("rtmp_url"),
  rtmpKey: document.getElementById("rtmp_key"),
  saveBtn: document.getElementById("save-btn"),
  signInHelper: document.getElementById("signin-helper"),
  ack: document.getElementById("ack"),
  continueBtn: document.getElementById("continue-btn"),
  changeDest: document.getElementById("change-dest"),
  startBtn: document.getElementById("start-btn"),
  stopBtn: document.getElementById("stop-btn"),
  helper: document.getElementById("transport-helper"),
  pill: document.getElementById("status-pill"),
};

const state = {
  beat: 1,
  previewOk: false,
  parsed: null,
  backend: "idle",
  error: "",
  configured: false,
  signInError: "",
};

let pollTimer = null;

function secrets() {
  return [els.rtmpUrl.value, els.rtmpKey.value];
}

function redact(text) {
  let out = String(text ?? "");
  for (const secret of secrets()) {
    if (secret && secret.length >= 3) out = out.split(secret).join("[redacted]");
  }
  return out.replace(/rtmps?:\/\/\S+/gi, "[redacted-rtmp]");
}

function clearDestFields() {
  els.rtmpUrl.value = "";
  els.rtmpKey.value = "";
  els.rtmpKey.type = "password";
}

function showBeat(n) {
  state.beat = n;
  els.beat1.classList.toggle("hidden", n !== 1);
  els.beat2.classList.toggle("hidden", n !== 2);
  els.beat3.classList.toggle("hidden", n !== 3);
}

function applyPreview(parsed) {
  state.parsed = parsed;
  state.previewOk = Boolean(parsed?.ok);
  els.pasteHelper.classList.toggle("hidden", parsed?.reason !== "youtube-first");

  for (const card of els.previewCards) {
    card.classList.toggle("hidden", !state.previewOk);
    if (!parsed?.ok) continue;
    const title = card.querySelector(".preview-title");
    const host = card.querySelector(".preview-host");
    const badge = card.querySelector(".preview-live-badge");
    const thumb = card.querySelector(".preview-thumb");
    title.textContent = parsed.title;
    host.textContent = parsed.host;
    badge.classList.toggle("hidden", !parsed.isLive);
    if (parsed.thumbnail) {
      thumb.src = parsed.thumbnail;
      thumb.alt = parsed.title;
      thumb.hidden = false;
    } else {
      thumb.removeAttribute("src");
      thumb.alt = "";
      thumb.hidden = true;
    }
  }
}

function clearPreview() {
  applyPreview(null);
}

function gate() {
  return {
    previewOk: state.previewOk,
    configured: state.configured,
    ack: els.ack.checked,
    state: state.backend,
  };
}

function render() {
  const status = pillFor({ previewOk: state.previewOk, state: state.backend });
  els.pill.dataset.status = status;
  els.pill.textContent = pillLabel(status);

  els.signInHelper.textContent = state.signInError || SIGNIN_HELPER;
  els.saveBtn.disabled = !(els.rtmpUrl.value.trim() && els.rtmpKey.value);
  els.previewBtn.disabled = parseSourceUrl(els.source.value).reason === "youtube-first";
  els.continueBtn.disabled = !canContinue(gate());
  els.startBtn.disabled = !canStart(gate());
  els.stopBtn.disabled = !canStop({ state: state.backend });

  els.helper.textContent = transportHelper({
    backend: state.backend,
    error: state.error ? redact(state.error) : "",
  });
}

async function runPreview() {
  const parsed = parseSourceUrl(els.source.value);
  if (!parsed.ok) {
    applyPreview(parsed);
    render();
    return;
  }
  try {
    const result = await retransApi.preview(parsed.href);
    if (result.ok) {
      applyPreview({
        ...parsed,
        title: result.title,
        isLive: Boolean(result.is_live),
      });
    } else {
      applyPreview({ ok: false, reason: result.error || "invalid" });
    }
  } catch {
    applyPreview({ ok: false, reason: "invalid" });
  }
  render();
}

function invalidatePreviewIfSourceChanged() {
  if (!state.parsed?.ok) {
    const parsed = parseSourceUrl(els.source.value);
    els.pasteHelper.classList.toggle("hidden", parsed.reason !== "youtube-first");
    render();
    return;
  }
  const next = parseSourceUrl(els.source.value);
  if (!next.ok || next.href !== state.parsed.href) {
    state.previewOk = false;
    state.parsed = null;
    clearPreview();
  }
  const parsed = parseSourceUrl(els.source.value);
  els.pasteHelper.classList.toggle("hidden", parsed.reason !== "youtube-first");
  render();
}

function applyBackend(result) {
  if (!result) return;
  state.backend = backendFromResult(result);
  state.error = typeof result.error === "string" ? result.error : "";
  if (result.source_url && !state.previewOk) {
    els.source.value = result.source_url;
    applyPreview(parseSourceUrl(result.source_url));
    runPreview();
  }
  if (state.backend === "starting" || state.backend === "live") startPolling();
  else stopPolling();
  render();
}

/** Apply GET /api/live/status only when it is a real session payload. */
function applyStatus(result) {
  if (!isUsableStatus(result)) return;
  applyBackend(result);
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      applyStatus(await retransApi.status());
    } catch {
      /* status failure: keep current chrome; never flip to Error */
    }
  }, 1000);
}

function stopPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

els.previewBtn.addEventListener("click", runPreview);

els.source.addEventListener("input", invalidatePreviewIfSourceChanged);
els.source.addEventListener("blur", runPreview);
els.source.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    runPreview();
  }
});
els.rtmpUrl.addEventListener("input", render);
els.rtmpKey.addEventListener("input", render);
els.ack.addEventListener("change", render);

els.rtmpKey.addEventListener("blur", () => {
  els.rtmpKey.type = "password";
});

els.saveBtn.addEventListener("click", async () => {
  const rtmp_url = els.rtmpUrl.value.trim();
  const rtmp_key = els.rtmpKey.value;
  if (!rtmp_url || !rtmp_key) return;
  els.saveBtn.disabled = true;
  try {
    const result = await retransApi.saveCredentials({ rtmp_url, rtmp_key });
    if (result.ok && result.configured) {
      state.configured = true;
      state.signInError = "";
      clearDestFields();
      showBeat(2);
    } else {
      state.signInError = result.error || "save failed";
    }
  } catch {
    state.signInError = "save failed";
  } finally {
    render();
  }
});

els.continueBtn.addEventListener("click", () => {
  if (!canContinue(gate())) return;
  showBeat(3);
  render();
});

els.changeDest.addEventListener("click", (event) => {
  event.preventDefault();
  clearDestFields();
  state.signInError = "";
  showBeat(1);
  render();
});

els.startBtn.addEventListener("click", async () => {
  if (!canStart(gate())) return;
  els.startBtn.disabled = true;
  try {
    const result = await retransApi.start({
      source_url: els.source.value.trim(),
    });
    applyBackend(result);
  } catch {
    state.backend = "error";
    state.error = "start failed";
    render();
  }
});

els.stopBtn.addEventListener("click", async () => {
  if (!canStop({ state: state.backend })) return;
  els.stopBtn.disabled = true;
  try {
    applyBackend(await retransApi.stop());
  } catch {
    state.backend = "error";
    state.error = "stop failed";
    render();
  }
});

async function boot() {
  render();
  try {
    const creds = await retransApi.credentials();
    if (creds.httpStatus === 200 && creds.configured) state.configured = true;
  } catch {
    /* GET fail treated as not configured → Beat 1 */
  }
  try {
    applyStatus(await retransApi.status());
  } catch {
    /* boot status failure: stay Idle; keep idle transport helper */
  }
  if (!state.configured) {
    showBeat(1);
  } else if (state.backend === "starting" || state.backend === "live") {
    if (state.previewOk) els.ack.checked = true;
    showBeat(3);
  } else {
    showBeat(2);
  }
  render();
}

boot();
