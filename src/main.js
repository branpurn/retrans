import "./style.css";
import { parseSourceUrl } from "./sourceUrl.js";
import { backendFromResult, canStart, canStop, pillFor, pillLabel } from "./enablement.js";
import { retransApi } from "./retransApi.js";

const els = {
  source: document.getElementById("source_url"),
  previewBtn: document.getElementById("preview-btn"),
  pasteHelper: document.getElementById("paste-helper"),
  previewEmpty: document.getElementById("preview-empty"),
  previewFilled: document.getElementById("preview-filled"),
  thumb: document.getElementById("preview-thumb"),
  liveBadge: document.getElementById("preview-live-badge"),
  previewTitle: document.getElementById("preview-title"),
  previewHost: document.getElementById("preview-host"),
  rtmpUrl: document.getElementById("rtmp_url"),
  rtmpKey: document.getElementById("rtmp_key"),
  ack: document.getElementById("ack"),
  startBtn: document.getElementById("start-btn"),
  stopBtn: document.getElementById("stop-btn"),
  helper: document.getElementById("transport-helper"),
  pill: document.getElementById("status-pill"),
};

const state = {
  previewOk: false,
  parsed: null,
  backend: "idle",
  error: "",
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

function applyPreview(parsed) {
  state.parsed = parsed;
  state.previewOk = Boolean(parsed?.ok);
  els.pasteHelper.classList.toggle("hidden", parsed?.reason !== "youtube-first");
  els.previewEmpty.classList.toggle("hidden", state.previewOk);
  els.previewFilled.classList.toggle("hidden", !state.previewOk);

  if (!parsed?.ok) return;

  els.previewTitle.textContent = parsed.title;
  els.previewHost.textContent = parsed.host;
  els.liveBadge.classList.toggle("hidden", !parsed.isLive);
  if (parsed.thumbnail) {
    els.thumb.src = parsed.thumbnail;
    els.thumb.alt = parsed.title;
    els.thumb.hidden = false;
  } else {
    els.thumb.removeAttribute("src");
    els.thumb.alt = "";
    els.thumb.hidden = true;
  }
}

function clearPreview() {
  applyPreview(null);
  els.previewEmpty.classList.remove("hidden");
  els.previewFilled.classList.add("hidden");
}

function render() {
  const status = pillFor({ previewOk: state.previewOk, state: state.backend });
  els.pill.dataset.status = status;
  els.pill.textContent = pillLabel(status);

  els.startBtn.disabled = !canStart({
    previewOk: state.previewOk,
    rtmpUrl: els.rtmpUrl.value,
    rtmpKey: els.rtmpKey.value,
    ack: els.ack.checked,
    state: state.backend,
  });
  els.stopBtn.disabled = !canStop({ state: state.backend });

  if (state.backend === "live") {
    els.helper.textContent = "Retransmitting live to X";
  } else if (state.backend === "error" && state.error) {
    els.helper.textContent = redact(state.error);
  } else {
    els.helper.textContent = "Idle until preview + destination + ack";
  }
}

function runPreview() {
  const parsed = parseSourceUrl(els.source.value);
  if (!parsed.ok) {
    state.previewOk = false;
    state.parsed = parsed;
    if (state.backend === "idle" || state.backend === "stopped") {
      /* stay on current backend state */
    }
    applyPreview(parsed);
    if (parsed.reason === "youtube-first") {
      els.pasteHelper.classList.remove("hidden");
    }
    render();
    return;
  }
  applyPreview(parsed);
  render();
}

function invalidatePreviewIfSourceChanged() {
  if (!state.parsed?.ok) {
    const parsed = parseSourceUrl(els.source.value);
    els.pasteHelper.classList.toggle("hidden", parsed.reason !== "youtube-first");
    els.previewBtn.disabled = parsed.reason === "youtube-first";
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
  els.previewBtn.disabled = parsed.reason === "youtube-first";
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
  }
  if (state.backend === "starting" || state.backend === "live") startPolling();
  else stopPolling();
  render();
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      applyBackend(await retransApi.status());
    } catch {
      state.backend = "error";
      state.error = "status failed";
      render();
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
els.rtmpUrl.addEventListener("input", render);
els.rtmpKey.addEventListener("input", render);
els.ack.addEventListener("change", render);

els.rtmpKey.addEventListener("blur", () => {
  els.rtmpKey.type = "password";
});

els.startBtn.addEventListener("click", async () => {
  if (
    !canStart({
      previewOk: state.previewOk,
      rtmpUrl: els.rtmpUrl.value,
      rtmpKey: els.rtmpKey.value,
      ack: els.ack.checked,
      state: state.backend,
    })
  ) {
    return;
  }
  els.startBtn.disabled = true;
  try {
    const result = await retransApi.start({
      source_url: els.source.value.trim(),
      rtmp_url: els.rtmpUrl.value.trim(),
      rtmp_key: els.rtmpKey.value,
    });
    els.rtmpKey.value = "";
    els.rtmpKey.type = "password";
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
    applyBackend(await retransApi.status());
  } catch {
    render();
  }
}

boot();
