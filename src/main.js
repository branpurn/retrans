import "./style.css";
import { parseSourceUrl } from "./sourceUrl.js";
import {
  backendFromResult,
  canContinue,
  canStart,
  canStop,
  isUsableStatus,
  nextChrome,
  pillFor,
  pillLabel,
  transportHelper,
} from "./enablement.js";
import { retransApi } from "./retransApi.js";
import { YOUTUBE_FIRST_HELPER, isPreviewProbeFail, previewPaint } from "./previewChrome.js";
import { readField, writeField, writeSourceIfNeeded } from "./fields.js";
import {
  SIGNIN_HELPER,
  aggregateSessions,
  applyDeleteKey,
  applyKeysBoot,
  applyKeysPoll,
  applySaveSuccess,
  clearStuck,
  putKeyBody,
  sessionIsError,
  stickSessions,
  unusedKeys,
} from "./keysFlow.js";

const els = {
  beat1: document.getElementById("beat-1"),
  beat2: document.getElementById("beat-2"),
  beat3: document.getElementById("beat-3"),
  source: document.getElementById("source_url"),
  previewBtn: document.getElementById("preview-btn"),
  pasteHelper: document.getElementById("paste-helper"),
  previewCards: document.querySelectorAll("[data-preview]"),
  keyName: document.getElementById("key_name"),
  rtmpUrl: document.getElementById("rtmp_url"),
  rtmpKey: document.getElementById("rtmp_key"),
  advanced: document.getElementById("advanced-rtmp"),
  keyList: document.getElementById("key-list"),
  addKeyBtn: document.getElementById("add-key-btn"),
  addKeyLink: document.getElementById("add-key-link"),
  saveBtn: document.getElementById("save-btn"),
  signInHelper: document.getElementById("signin-helper"),
  signInHelp: document.getElementById("signin-help"),
  signInHelpBtn: document.getElementById("signin-help-btn"),
  keyPicker: document.getElementById("key_id"),
  ack: document.getElementById("ack"),
  continueBtn: document.getElementById("continue-btn"),
  changeDest: document.getElementById("change-dest"),
  dropAnother: document.getElementById("drop-another"),
  sessionList: document.getElementById("session-list"),
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
  keys: [],
  justSaved: false,
  adding: false,
  selectedKeyId: "",
  sessions: [],
  stuckErrors: {},
  signInError: "",
};

let pollTimer = null;

function secrets() {
  return [readField(els.rtmpUrl), readField(els.rtmpKey)];
}

function redact(text) {
  let out = String(text ?? "");
  for (const secret of secrets()) {
    if (secret && secret.length >= 3) out = out.split(secret).join("[redacted]");
  }
  return out.replace(/rtmps?:\/\/\S+/gi, "[redacted-rtmp]");
}

function clearDestFields() {
  writeField(els.keyName, "");
  writeField(els.rtmpUrl, "");
  writeField(els.rtmpKey, "");
  els.rtmpKey.type = "password";
  if (els.advanced) els.advanced.open = false;
}

function showBeat(n) {
  state.beat = n;
  els.beat1.classList.toggle("hidden", n !== 1);
  els.beat2.classList.toggle("hidden", n !== 2);
  els.beat3.classList.toggle("hidden", n !== 3);
}

function applyChrome(next) {
  state.keys = next.keys;
  state.justSaved = Boolean(next.justSaved);
  state.adding = Boolean(next.adding);
  showBeat(next.beat);
}

function applyPaint(model, parsed) {
  state.parsed = parsed;
  state.previewOk = Boolean(model.previewOk);
  const helper = model.helper || "";
  els.pasteHelper.textContent = helper || YOUTUBE_FIRST_HELPER;
  els.pasteHelper.classList.toggle("hidden", !helper);

  // Title/host stay on the preview card — never paint them onto #source_url.
  for (const card of els.previewCards) {
    card.classList.toggle("hidden", !model.showCard);
    const title = card.querySelector(".preview-title");
    const host = card.querySelector(".preview-host");
    const badge = card.querySelector(".preview-live-badge");
    const thumb = card.querySelector(".preview-thumb");
    title.textContent = model.title;
    host.textContent = model.host;
    badge.classList.toggle("hidden", model.showLiveBadge !== true);
    if (model.thumbnail) {
      thumb.src = model.thumbnail;
      thumb.alt = model.title;
      thumb.hidden = false;
    } else {
      thumb.removeAttribute("src");
      thumb.alt = "";
      thumb.hidden = true;
    }
  }
}

function applyPreview(parsed, result = null) {
  applyPaint(previewPaint({ parsed, result }), parsed);
}

function clearPreview() {
  applyPaint(previewPaint({ parsed: null, result: null }), null);
}

function selectedBusy() {
  return unusedKeys(state.keys, state.sessions).every((key) => key.id !== state.selectedKeyId)
    && Boolean(state.selectedKeyId);
}

function gate() {
  const unused = unusedKeys(state.keys, state.sessions);
  const selectedKeyId = unused.some((key) => key.id === state.selectedKeyId)
    ? state.selectedKeyId
    : "";
  return {
    previewOk: state.previewOk,
    configured: state.keys.length > 0 || state.justSaved,
    ack: els.ack.checked,
    state: state.backend,
    selectedKeyId,
    selectedBusy: Boolean(selectedKeyId) && selectedBusy(),
  };
}

function renderKeyList() {
  els.keyList.replaceChildren();
  for (const key of state.keys) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "key-name";
    name.textContent = key.name;
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "Delete";
    del.addEventListener("click", () => onDeleteKey(key.id));
    li.append(name, del);
    els.keyList.append(li);
  }
}

function renderKeyPicker() {
  const unused = unusedKeys(state.keys, state.sessions);
  const previous = state.selectedKeyId;
  els.keyPicker.replaceChildren();
  for (const key of unused) {
    const opt = document.createElement("option");
    opt.value = key.id;
    opt.textContent = key.name;
    els.keyPicker.append(opt);
  }
  if (unused.some((key) => key.id === previous)) {
    els.keyPicker.value = previous;
    state.selectedKeyId = previous;
  } else if (unused[0]) {
    state.selectedKeyId = unused[0].id;
    els.keyPicker.value = unused[0].id;
  } else {
    state.selectedKeyId = "";
  }
}

function sessionErrorText() {
  const row = state.sessions.find(sessionIsError);
  return row?.error || state.error || "";
}

function renderSessions() {
  els.sessionList.replaceChildren();
  for (const sess of state.sessions) {
    const li = document.createElement("li");
    const source = document.createElement("span");
    source.className = "sess-source";
    source.textContent = sess.source_url || "";
    const name = document.createElement("span");
    name.className = "sess-name";
    name.textContent = sess.name || "";
    const pill = document.createElement("p");
    const status = pillFor({ previewOk: false, state: sess.state });
    pill.className = "pill";
    pill.dataset.status = status;
    pill.textContent = pillLabel(status);
    const stop = document.createElement("button");
    stop.type = "button";
    stop.className = "btn-stop";
    stop.textContent = "Stop";
    stop.disabled = !canStop({ state: sess.state });
    stop.addEventListener("click", () => onStopSession(sess));
    li.append(source, name, pill, stop);
    els.sessionList.append(li);
  }
}

function render() {
  const status = pillFor({ previewOk: state.previewOk, state: state.backend });
  els.pill.dataset.status = status;
  els.pill.textContent = pillLabel(status);

  els.signInHelper.textContent = state.signInError || SIGNIN_HELPER;
  els.saveBtn.disabled = !readField(els.rtmpKey);
  els.previewBtn.disabled = parseSourceUrl(readField(els.source)).reason === "youtube-first";
  els.continueBtn.disabled = !canContinue(gate());
  els.startBtn.disabled = !canStart(gate());
  const hasSessionStop = state.sessions.some((sess) => canStop({ state: sess.state }));
  els.stopBtn.disabled = !canStop({ state: state.backend }) && !hasSessionStop;

  renderKeyList();
  renderKeyPicker();
  renderSessions();

  els.helper.textContent = transportHelper({
    backend: state.backend,
    error: sessionErrorText() ? redact(sessionErrorText()) : "",
  });
}

async function runPreview() {
  const parsed = parseSourceUrl(readField(els.source));
  if (!parsed.ok) {
    applyPreview(parsed);
    render();
    return;
  }
  // Field stays el.value (one URL). Do not write result.source_url / parsed.href.
  try {
    const result = await retransApi.preview(parsed.href);
    if (result.error) result.error = redact(result.error);
    // 502: Beat 2 Error helper as-is. Hide card. Never Error pill. Never empty title card.
    applyPreview(parsed, result);
    if (isPreviewProbeFail(result) || result.httpStatus === 502 || !result.ok) {
      state.previewOk = false;
    }
  } catch {
    applyPreview(parsed, { ok: false, httpStatus: 502, error: "" });
    state.previewOk = false;
  }
  render();
}

function invalidatePreviewIfSourceChanged() {
  const next = parseSourceUrl(readField(els.source));
  if (state.parsed?.ok && next.ok && next.href === state.parsed.href) {
    render();
    return;
  }
  if (state.parsed?.ok && (!next.ok || next.href !== state.parsed.href)) {
    state.previewOk = false;
    state.parsed = null;
    clearPreview();
  }
  applyPreview(next);
  render();
}

function applyBackend(result) {
  if (!result) return;
  applyOperator(result, "command");
}

/** Apply GET /api/live/status only when it is a real session payload. */
function applyStatus(result) {
  if (!isUsableStatus(result)) return;
  applyOperator(result, "status");
}

function applyOperator(result, source) {
  if (Array.isArray(result.sessions)) {
    const stuck = stickSessions(state.sessions, result.sessions, state.stuckErrors);
    state.sessions = stuck.sessions;
    state.stuckErrors = stuck.stuckErrors;
  }
  const aggregated = {
    ...result,
    state: aggregateSessions(state.sessions, result.state),
    error: sessionErrorText() || result.error,
  };
  const next = nextChrome(
    { backend: state.backend, error: state.error },
    aggregated,
    source,
  );
  const stuckError =
    source === "status" &&
    state.backend === "error" &&
    backendFromResult(aggregated) !== "error";
  state.backend = next.backend;
  state.error = next.error;
  if (stuckError) {
    render();
    return;
  }
  if (result.source_url && !state.previewOk) {
    // Restore only when the typed value is empty/wrong — never append, never rewrite the same URL.
    writeSourceIfNeeded(els.source, result.source_url);
    runPreview();
  }
  const liveish = state.sessions.some((sess) => sess.state === "starting" || sess.state === "live");
  if (state.backend === "starting" || state.backend === "live" || liveish) startPolling();
  else stopPolling();
  render();
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      applyStatus(await retransApi.status());
    } catch {
      /* status failure: keep current chrome; never flip to Error */
    }
    try {
      applyChrome(applyKeysPoll(state, await retransApi.listKeys()));
    } catch {
      /* empty/slow GET keys must not snap Beat 2 after justSaved */
      applyChrome(applyKeysPoll(state, { httpStatus: 0, keys: [] }));
    }
  }, 1000);
}

function stopPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

function goAddKey() {
  clearDestFields();
  state.signInError = "";
  state.adding = state.keys.length > 0;
  showBeat(1);
  render();
}

async function onDeleteKey(id) {
  if (!window.confirm("Delete this key?")) return;
  try {
    await retransApi.deleteKey(id);
  } catch {
    /* delete failed — still drop locally if last key so Beat 1 is reachable */
  }
  applyChrome(applyDeleteKey(state, id));
  render();
}

async function onStopSession(sess) {
  if (!canStop({ state: sess.state })) return;
  try {
    applyBackend(await retransApi.stop({ session_id: sess.session_id, key_id: sess.key_id }));
    state.stuckErrors = clearStuck(state.stuckErrors, sess);
    state.sessions = state.sessions.filter((row) => {
      if (sess.session_id && row.session_id === sess.session_id) return false;
      if (sess.key_id && row.key_id === sess.key_id && row.state === "error") return false;
      return true;
    });
  } catch {
    state.backend = "error";
    state.error = "stop failed";
  }
  render();
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
els.rtmpKey.addEventListener("input", render);
els.keyName.addEventListener("input", render);
els.ack.addEventListener("change", render);
els.keyPicker.addEventListener("change", () => {
  state.selectedKeyId = els.keyPicker.value;
  render();
});

els.rtmpKey.addEventListener("blur", () => {
  els.rtmpKey.type = "password";
});

els.signInHelpBtn.addEventListener("click", () => {
  const open = els.signInHelp.classList.toggle("hidden");
  els.signInHelpBtn.setAttribute("aria-expanded", open ? "false" : "true");
});

els.addKeyBtn.addEventListener("click", goAddKey);
els.addKeyLink.addEventListener("click", (event) => {
  event.preventDefault();
  goAddKey();
});

els.saveBtn.addEventListener("click", async () => {
  const rtmp_key = readField(els.rtmpKey);
  if (!rtmp_key) return;
  const adding = state.adding || state.keys.length > 0;
  const body = putKeyBody({
    name: readField(els.keyName),
    rtmp_key,
    rtmp_url: els.advanced?.open ? readField(els.rtmpUrl).trim() : "",
    keys: state.keys,
  });
  els.saveBtn.disabled = true;
  try {
    const result = await retransApi.saveKey(body);
    if (result.ok && result.id) {
      state.signInError = "";
      applyChrome(applySaveSuccess(state, { id: result.id, name: result.name }, { adding }));
      clearDestFields();
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
  goAddKey();
});

els.dropAnother.addEventListener("click", (event) => {
  event.preventDefault();
  const unused = unusedKeys(state.keys, state.sessions);
  if (unused.length === 0) {
    goAddKey();
    return;
  }
  state.selectedKeyId = unused[0].id;
  showBeat(2);
  render();
});

els.startBtn.addEventListener("click", async () => {
  if (!canStart(gate())) return;
  els.startBtn.disabled = true;
  try {
    const result = await retransApi.start({
      source_url: readField(els.source).trim(),
      key_id: state.selectedKeyId,
    });
    applyBackend(result);
  } catch {
    state.backend = "error";
    state.error = "start failed";
    render();
  }
});

els.stopBtn.addEventListener("click", async () => {
  if (!canStop({ state: state.backend }) && !state.sessions.some((sess) => canStop({ state: sess.state }))) {
    return;
  }
  els.stopBtn.disabled = true;
  const sess = state.sessions.find((row) => canStop({ state: row.state }));
  try {
    applyBackend(
      await retransApi.stop(
        sess ? { session_id: sess.session_id, key_id: sess.key_id } : {},
      ),
    );
    if (sess) state.stuckErrors = clearStuck(state.stuckErrors, sess);
    state.error = "";
  } catch {
    state.backend = "error";
    state.error = "stop failed";
    render();
  }
});

async function boot() {
  render();
  try {
    applyChrome(applyKeysBoot(await retransApi.listKeys()));
  } catch {
    applyChrome(applyKeysBoot({ httpStatus: 0, keys: [] }));
  }
  try {
    applyStatus(await retransApi.status());
  } catch {
    /* boot status failure: stay Idle; keep idle transport helper */
  }
  if (state.keys.length === 0 && !state.justSaved) {
    showBeat(1);
  } else if (state.backend === "starting" || state.backend === "live" || state.sessions.some((sess) => sess.state === "starting" || sess.state === "live" || sess.state === "error")) {
    if (state.previewOk) els.ack.checked = true;
    showBeat(3);
  } else if (state.beat === 1 && (state.keys.length > 0 || state.justSaved) && !state.adding) {
    showBeat(2);
  }
  render();
}

boot();
