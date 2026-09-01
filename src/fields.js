/**
 * Operator field read/write. Displayed text is always el.value (or empty).
 * Replace only — never append, never placeholder+value, never URL+URL.
 */

import { parseSourceUrl } from "./sourceUrl.js";

export const SOURCE_PLACEHOLDER = "Paste YouTube live URL";

export function readField(el) {
  return el.value;
}

/** Collapse URL+URL / current+next into one URL. */
function singleUrl(current, next) {
  const value = next == null ? "" : String(next);
  const have = current == null ? "" : String(current);
  if (have && value === have + have) return have;
  if (have && value.startsWith(have)) {
    const extra = value.slice(have.length);
    if (extra === have || /^https?:\/\//i.test(extra)) return have;
  }
  if (value.length >= 8 && value.length % 2 === 0) {
    const half = value.slice(0, value.length / 2);
    if (half && value === half + half && /^https?:\/\//i.test(half)) return half;
  }
  return value;
}

export function sameSourceValue(current, next) {
  const a = String(current ?? "").trim();
  const b = String(next ?? "").trim();
  if (a === b) return true;
  if (!a || !b) return false;
  const pa = parseSourceUrl(a);
  const pb = parseSourceUrl(b);
  return Boolean(pa.ok && pb.ok && pa.href === pb.href);
}

/**
 * Replace el.value. Never append.
 * Skip when already that string, or when asked to write the placeholder
 * over a real typed value (RTMP leftover + Drop-link).
 */
export function writeField(el, next) {
  const placeholder = el.getAttribute("placeholder") ?? "";
  const current = el.value ?? "";
  let value = next == null ? "" : String(next);
  if (placeholder && value === placeholder && current && current !== placeholder) {
    return current;
  }
  value = singleUrl(current, value);
  if (current === value) {
    return current;
  }
  el.value = value;
  return el.value;
}

/**
 * After Preview / status restore: write only when the stored value is
 * empty or actually wrong. Do not append result.source_url / parsed.href.
 */
export function writeSourceIfNeeded(el, next) {
  const current = readField(el);
  const value = next == null ? "" : String(next);
  if (!value) return current;
  if (sameSourceValue(current, value)) return current;
  return writeField(el, value);
}

/**
 * Preview-path field policy. Reads the typed URL; may replace if wrong.
 * Second call with the same URL must leave el.value unchanged (one URL).
 */
export function applyPreviewSource(el, result = {}, parsed = null) {
  const incoming = [result?.source_url, parsed?.href];
  for (const next of incoming) {
    if (typeof next === "string" && next) writeSourceIfNeeded(el, next);
  }
  return readField(el);
}
