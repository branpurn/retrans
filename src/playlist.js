/**
 * Ordered playlist of YouTube URLs. Same named key_id for the whole list.
 * Start with {source_urls, key_id} when 1+ items (VOD + live).
 * Single live {source_url, key_id} stays on the API client — UI does not use it
 * once the playlist has items.
 */

import { parseSourceUrl } from "./sourceUrl.js";

export function parsePlaylistUrl(raw) {
  const parsed = parseSourceUrl(raw);
  return parsed.ok ? parsed.href : "";
}

/** Append a YouTube URL. Duplicates stay in place (no second copy). */
export function addUrl(list, raw) {
  const href = parsePlaylistUrl(raw);
  if (!href) return list.slice();
  const current = Array.isArray(list) ? list : [];
  if (current.includes(href)) return current.slice();
  return [...current, href];
}

export function removeAt(list, index) {
  const current = Array.isArray(list) ? list : [];
  if (!Number.isInteger(index) || index < 0 || index >= current.length) {
    return current.slice();
  }
  return current.filter((_, i) => i !== index);
}

export function moveUrl(list, index, delta) {
  const current = Array.isArray(list) ? list.slice() : [];
  const next = index + delta;
  if (
    !Number.isInteger(index) ||
    !Number.isInteger(delta) ||
    index < 0 ||
    next < 0 ||
    index >= current.length ||
    next >= current.length
  ) {
    return current;
  }
  const swap = current[index];
  current[index] = current[next];
  current[next] = swap;
  return current;
}

/**
 * URLs the operator will start. Playlist wins. If the list is empty, the
 * typed field becomes a one-item playlist when it parses as YouTube.
 */
export function playlistUrls(list, typed = "") {
  const current = Array.isArray(list) ? list.filter(Boolean) : [];
  if (current.length > 0) return current.slice();
  const href = parsePlaylistUrl(typed);
  return href ? [href] : [];
}

/**
 * POST /api/live/start body.
 * 1+ source_urls → {source_urls, key_id} (never also source_url).
 * Else the live-only single {source_url, key_id} path.
 * Never destination secrets.
 */
export function startBody({ source_url, source_urls, key_id } = {}) {
  if (Array.isArray(source_urls) && source_urls.length > 0) {
    return { source_urls: source_urls.map(String), key_id };
  }
  return { source_url, key_id };
}

export function sessionIndex(session) {
  const n = session?.source_index;
  return Number.isInteger(n) && n >= 0 ? n : 0;
}

/** Compact Beat 3 position: `{source_index+1}/{n}` e.g. `2/5`. */
export function playlistPos(session, total = 0) {
  const n = Number.isInteger(total) && total > 0 ? total : 0;
  if (!n) return "";
  return `${sessionIndex(session) + 1}/${n}`;
}

/**
 * Retrans beat: current source + compact position. No editor maze.
 */
export function nowPlayingCopy(session, total = 0) {
  return playlistPos(session, total);
}

/** Exhausted playlist is Idle/Stopped — never invent Error from a natural end. */
export function isNaturalEnd(result) {
  if (!result) return false;
  if (result.state === "error") return false;
  if (result.state !== "idle" && result.state !== "stopped") return false;
  const error = result.error;
  return error == null || (typeof error === "string" && error.trim() === "");
}
