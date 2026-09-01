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
  addUrl,
  isNaturalEnd,
  moveUrl,
  playlistPos,
  playlistUrls,
  removeAt,
} from "./playlist.js";
import {
  KEYS_HELPER,
  aggregateSessions,
  applyDeleteKey,
  applyKeysBoot,
  applyKeysPoll,
  applySaveSuccess,
  applySelectKey,
  applyStartEdit,
  clearStuck,
  putKeyBody,
  sessionIsError,
  stickSessions,
  unusedKeys,
} from "./keysFlow.js";
import { NAMED_TEE, OUTBOUND_LABEL, attachPlayer, playerShouldAttach } from "./player.js";
import { paintPaneMenu, paneAfterMenu, paneFromClick } from "./paneMenu.js";

const els = {
  paneMenu: document.getElementById("pane-menu"),
  beat1: document.getElementById("beat-1"),
  beat2: document.getElementById("beat-2"),
  beat3: document.getElementById("beat-3"),
  source: document.getElementById("source_url"),
  previewBtn: document.getElementById("preview-btn"),
  addUrlBtn: document.getElementById("add-url-btn"),
  playlist: document.getElementById("playlist"),
  playlistNow: document.getElementById("playlist-now"),
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
  keysHelper: document.getElementById("keys-helper"),
  keysHelp: document.getElementById("keys-help"),
  keysHelpBtn: document.getElementById("keys-help-btn"),
  keyPicker: document.getElementById("key_id"),
  ack: document.getElementById("ack"),
  continueBtn: document.getElementById("continue-btn"),
  changeDest: document.getElementById("change-dest"),
  dropAnother: document.getElementById("drop-another"),
  sessionList: document.getElementById("session-list"),
  outbound: document.getElementById("outbound"),
  player: document.getElementById("outbound-player"),
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
  editingId: "",
  selectedKeyId: "",
  sessions: [],
  stuckErrors: {},
  keysError: "",
  playlist: [],
  selectedPlIndex: -1,
  previewByUrl: {},
  currentSource: "",
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
  paintPaneMenu(els.paneMenu, n);
}

function applyChrome(next) {
  state.keys = next.keys;
  state.justSaved = Boolean(next.justSaved);
  state.adding = Boolean(next.adding);
  if ("editingId" in next) state.editingId = next.editingId || "";
  if ("selectedKeyId" in next) state.selectedKeyId = next.selectedKeyId || "";
  showBeat(next.beat);
}

function applyPaint(model, parsed) {
  state.parsed = parsed;
  state.previewOk = Boolean(model.previewOk);
  if (parsed?.ok && parsed.href) {
    state.previewByUrl[parsed.href] = Boolean(model.previewOk);
  }
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

function playlistReady() {
  const urls = playlistUrls(state.playlist, readField(els.source).trim());
  if (urls.length === 0) return false;
  return urls.every((href) => state.previewByUrl[href] === true);
}

function gate() {
  const unused = unusedKeys(state.keys, state.sessions);
  const kept = Boolean(state.selectedKeyId) && state.keys.some((key) => key.id === state.selectedKeyId);
  const selectedKeyId = kept ? state.selectedKeyId : "";
  const busy = Boolean(selectedKeyId) && unused.every((key) => key.id !== selectedKeyId);
  return {
    previewOk: playlistReady() || (state.previewOk && state.playlist.length === 0),
    configured: state.keys.length > 0 || state.justSaved,
    ack: els.ack.checked,
    state: state.backend,
    selectedKeyId: busy ? "" : selectedKeyId,
    selectedBusy: busy,
  };
}

function renderKeyList() {
  els.keyList.replaceChildren();
  for (const key of state.keys) {
    const li = document.createElement("li");
    if (key.id === state.selectedKeyId) li.className = "is-selected";
    const name = document.createElement("button");
    name.type = "button";
    name.className = "key-name";
    name.textContent = key.name;
    name.addEventListener("click", () => onEditKey(key.id));
    const actions = document.createElement("div");
    actions.className = "key-actions";
    const select = document.createElement("button");
    select.type = "button";
    select.textContent = "Select";
    select.addEventListener("click", () => onSelectKey(key.id));
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Open/Edit";
    edit.addEventListener("click", () => onEditKey(key.id));
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "Delete";
    del.addEventListener("click", () => onDeleteKey(key.id));
    actions.append(select, edit, del);
    li.append(name, actions);
    els.keyList.append(li);
  }
}

function renderKeyPicker() {
  const unused = unusedKeys(state.keys, state.sessions);
  const previous = state.selectedKeyId;
  const kept = state.keys.find((key) => key.id === previous);
  const options = unused.slice();
  // Same key_id for the whole run — do not re-Select when that key is in use.
  if (kept && !options.some((key) => key.id === kept.id)) options.unshift(kept);
  els.keyPicker.replaceChildren();
  for (const key of options) {
    const opt = document.createElement("option");
    opt.value = key.id;
    opt.textContent = key.name;
    els.keyPicker.append(opt);
  }
  if (kept) {
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

function renderPlaylist() {
  els.playlist.replaceChildren();
  state.playlist.forEach((href, index) => {
    const li = document.createElement("li");
    if (index === state.selectedPlIndex) li.className = "is-selected";
    const pick = document.createElement("button");
    pick.type = "button";
    pick.className = "pl-url";
    pick.textContent = href;
    pick.addEventListener("click", () => onSelectPlaylist(index));
    const actions = document.createElement("div");
    actions.className = "pl-actions";
    const up = document.createElement("button");
    up.type = "button";
    up.textContent = "Up";
    up.disabled = index === 0;
    up.addEventListener("click", () => onMovePlaylist(index, -1));
    const down = document.createElement("button");
    down.type = "button";
    down.textContent = "Down";
    down.disabled = index === state.playlist.length - 1;
    down.addEventListener("click", () => onMovePlaylist(index, 1));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => onRemovePlaylist(index));
    actions.append(up, down, remove);
    li.append(pick, actions);
    els.playlist.append(li);
  });
}

function activeSession() {
  return (
    state.sessions.find((sess) => sess.state === "starting" || sess.state === "live") ||
    state.sessions.find((sess) => sess.source_url) ||
    null
  );
}

function renderNowPlaying() {
  const sess = activeSession();
  const total = state.playlist.length;
  const pos = playlistPos(sess || { source_index: 0 }, total);
  const url = sess?.source_url || "";
  if (!pos && !url) {
    els.playlistNow.textContent = "";
    els.playlistNow.classList.add("hidden");
    return;
  }
  els.playlistNow.textContent = [pos, url].filter(Boolean).join(" ");
  els.playlistNow.classList.remove("hidden");
}

function renderSessions() {
  els.sessionList.replaceChildren();
  for (const sess of state.sessions) {
    const li = document.createElement("li");
    const source = document.createElement("span");
    source.className = "sess-source";
    const pos = playlistPos(sess, state.playlist.length);
    source.textContent = pos ? `${pos} ${sess.source_url || ""}` : sess.source_url || "";
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
    if (playerShouldAttach({ backend: sess.state })) {
      const wrap = document.createElement("div");
      wrap.className = "outbound";
      const label = document.createElement("p");
      label.className = "outbound-label";
      label.textContent = OUTBOUND_LABEL;
      const video = document.createElement("video");
      video.className = "outbound-player";
      video.controls = true;
      video.playsInline = true;
      video.preload = "none";
      video.setAttribute("aria-label", OUTBOUND_LABEL);
      attachPlayer(video, { attach: true, src: sess.outbound_url || NAMED_TEE });
      wrap.append(label, video);
      li.append(wrap);
    }
    els.sessionList.append(li);
  }
}

function render() {
  const status = pillFor({ previewOk: state.previewOk, state: state.backend });
  els.pill.dataset.status = status;
  els.pill.textContent = pillLabel(status);

  els.keysHelper.textContent = state.keysError || KEYS_HELPER;
  els.saveBtn.disabled = !readField(els.rtmpKey);
  els.previewBtn.disabled = parseSourceUrl(readField(els.source)).reason === "youtube-first";
  els.addUrlBtn.disabled = parseSourceUrl(readField(els.source)).reason === "youtube-first";
  els.continueBtn.disabled = !canContinue(gate());
  const urls = playlistUrls(state.playlist, readField(els.source).trim());
  els.startBtn.disabled = !canStart(gate()) || urls.length === 0;
  const hasSessionStop = state.sessions.some((sess) => canStop({ state: sess.state }));
  els.stopBtn.disabled = !canStop({ state: state.backend }) && !hasSessionStop;

  renderKeyList();
  renderKeyPicker();
  renderPlaylist();
  renderSessions();
  renderNowPlaying();
  paintPaneMenu(els.paneMenu, state.beat);
  const rowLive = state.sessions.some((sess) => playerShouldAttach({ backend: sess.state }));
  const attach = !rowLive && playerShouldAttach({ backend: state.backend, sessions: state.sessions });
  els.outbound?.classList.toggle("hidden", !attach);
  attachPlayer(els.player, {
    attach,
    src: activeSession()?.outbound_url || NAMED_TEE,
  });

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
  if (
    source === "status" &&
    isNaturalEnd({ ...aggregated, error: result.error }) &&
    state.backend === "error" &&
    !stuckError
  ) {
    state.backend = aggregated.state === "idle" ? "idle" : "stopped";
    state.error = "";
  }
  if (stuckError) {
    render();
    return;
  }
  const sess = activeSession();
  if (sess?.source_url && sess.source_url !== state.currentSource) {
    state.currentSource = sess.source_url;
    const parsed = parseSourceUrl(sess.source_url);
    if (parsed.ok) {
      retransApi.preview(parsed.href).then((preview) => {
        if (preview.error) preview.error = redact(preview.error);
        applyPreview(parsed, preview);
        render();
      }).catch(() => {});
    }
  }
  if (result.source_url && !state.previewOk && state.playlist.length === 0) {
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

function goKeysPanel({ add = false } = {}) {
  clearDestFields();
  state.keysError = "";
  state.editingId = "";
  state.adding = Boolean(add && state.keys.length > 0);
  showBeat(1);
  render();
}

function goAddKey() {
  goKeysPanel({ add: true });
}

function onSelectKey(id) {
  applyChrome(applySelectKey(state, id));
  render();
}

function onEditKey(id) {
  const key = state.keys.find((row) => row.id === id);
  if (!key) return;
  applyChrome(applyStartEdit(state, id));
  writeField(els.keyName, key.name);
  writeField(els.rtmpKey, "");
  writeField(els.rtmpUrl, "");
  if (els.advanced) els.advanced.open = false;
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

function commitTypedUrl() {
  const next = addUrl(state.playlist, readField(els.source).trim());
  if (next.length === state.playlist.length) return state.playlist;
  state.playlist = next;
  state.selectedPlIndex = next.length - 1;
  return state.playlist;
}

function onAddUrl() {
  const before = state.playlist.length;
  commitTypedUrl();
  if (state.playlist.length === before) {
    const parsed = parseSourceUrl(readField(els.source));
    applyPreview(parsed);
    render();
    return;
  }
  runPreview();
}

function onSelectPlaylist(index) {
  const href = state.playlist[index];
  if (!href) return;
  state.selectedPlIndex = index;
  writeField(els.source, href);
  runPreview();
}

function onMovePlaylist(index, delta) {
  const next = moveUrl(state.playlist, index, delta);
  const href = state.playlist[index];
  state.playlist = next;
  state.selectedPlIndex = href ? next.indexOf(href) : -1;
  render();
}

function onRemovePlaylist(index) {
  state.playlist = removeAt(state.playlist, index);
  if (state.selectedPlIndex === index) state.selectedPlIndex = -1;
  else if (state.selectedPlIndex > index) state.selectedPlIndex -= 1;
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

els.paneMenu.addEventListener("click", (event) => {
  const pane = paneFromClick(event.target);
  if (!pane) return;
  // Menu never Stops. Drop link with no selected key stays on Keys.
  showBeat(paneAfterMenu(pane, state.selectedKeyId, state.beat));
  render();
});

els.previewBtn.addEventListener("click", runPreview);
els.addUrlBtn.addEventListener("click", onAddUrl);

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

els.keysHelpBtn.addEventListener("click", () => {
  const open = els.keysHelp.classList.toggle("hidden");
  els.keysHelpBtn.setAttribute("aria-expanded", open ? "false" : "true");
});

els.addKeyBtn.addEventListener("click", goAddKey);
els.addKeyLink.addEventListener("click", (event) => {
  event.preventDefault();
  goAddKey();
});

els.saveBtn.addEventListener("click", async () => {
  const rtmp_key = readField(els.rtmpKey);
  if (!rtmp_key) return;
  const editing = Boolean(state.editingId);
  const adding = !editing && (state.adding || state.keys.length > 0);
  const body = putKeyBody({
    id: state.editingId || undefined,
    name: readField(els.keyName),
    rtmp_key,
    rtmp_url: els.advanced?.open ? readField(els.rtmpUrl).trim() : "",
    keys: state.keys,
  });
  els.saveBtn.disabled = true;
  try {
    const result = await retransApi.saveKey(body);
    if (result.ok && result.id) {
      state.keysError = "";
      applyChrome(
        applySaveSuccess(state, { id: result.id, name: result.name }, { adding, editing }),
      );
      clearDestFields();
    } else {
      state.keysError = result.error || "save failed";
    }
  } catch {
    state.keysError = "save failed";
  } finally {
    render();
  }
});

els.continueBtn.addEventListener("click", () => {
  if (!canContinue(gate())) return;
  commitTypedUrl();
  showBeat(3);
  render();
});

els.changeDest.addEventListener("click", (event) => {
  event.preventDefault();
  goKeysPanel({ add: false });
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
    const source_urls = playlistUrls(state.playlist, readField(els.source).trim());
    const result = await retransApi.start({
      source_urls,
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
  const liveish = state.sessions.some(
    (sess) => sess.state === "starting" || sess.state === "live" || sess.state === "error",
  );
  if (state.backend === "starting" || state.backend === "live" || liveish) {
    if (state.previewOk) els.ack.checked = true;
    showBeat(3);
  } else {
    showBeat(state.beat);
  }
  render();
}

boot();
