/**
 * Beat 2 preview chrome. Consume design/primary-flow.md.
 * GET /api/live/preview only — no second API.
 *
 * 502 {ok:false, error}: hide card, no LIVE badge, helper = API error as-is
 * (caller redacts rtmp secrets). previewOk false. Do not flip the status pill.
 * 200 ok empty title still host-only / empty card — that rule is not for 502.
 */

export const YOUTUBE_FIRST_HELPER = "YouTube first";

function trimmedError(result) {
  return typeof result?.error === "string" ? result.error.trim() : "";
}

/** HTTP 502, or ok:false with httpStatus 502 / yt-dlp probe-fail error. */
export function isPreviewProbeFail(result) {
  if (!result) return false;
  if (result.httpStatus === 502) return true;
  if (result.ok) return false;
  return /preview probe failed|yt-dlp preview probe failed/i.test(trimmedError(result));
}

/**
 * Beat 2 Error helper for preview 502.
 * API error as-is (already redacted). Do not invent status failed / clip copy.
 */
export function previewHelperCopy(result) {
  return trimmedError(result);
}

function hiddenCard(helper = "") {
  return {
    previewOk: false,
    showCard: false,
    title: "",
    host: "",
    thumbnail: "",
    showLiveBadge: false,
    helper,
  };
}

/**
 * Paint model for Beat 2 / Beat 3 preview cards.
 * @param {{ parsed?: object | null, result?: object | null }} args
 */
export function previewPaint({ parsed = null, result = null } = {}) {
  if (isPreviewProbeFail(result) || result?.httpStatus === 502) {
    return hiddenCard(previewHelperCopy(result));
  }

  if (parsed && !parsed.ok) {
    return hiddenCard(parsed.reason === "youtube-first" ? YOUTUBE_FIRST_HELPER : "");
  }

  if (!result) {
    return hiddenCard("");
  }

  if (!result.ok) {
    const error = trimmedError(result);
    const helper =
      parsed?.reason === "youtube-first" || error === "YouTube first"
        ? YOUTUBE_FIRST_HELPER
        : error;
    return hiddenCard(helper);
  }

  const title =
    typeof result.title === "string" && result.title.trim() ? result.title.trim() : "";
  return {
    previewOk: true,
    showCard: true,
    title,
    host: parsed?.host || "",
    thumbnail: typeof parsed?.thumbnail === "string" ? parsed.thumbnail : "",
    showLiveBadge: result.is_live === true,
    helper: "",
  };
}
