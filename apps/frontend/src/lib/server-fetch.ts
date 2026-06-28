/**
 * Server-side `fetch` with bounded retry for transient failures.
 *
 * SSR pages (force-dynamic server components) fetch the backend directly with
 * `fetch`. On a brief backend/DB blip the backend returns a 5xx — or the
 * connection itself fails — and the page throws, tripping the dashboard error
 * boundary ("Something went wrong. The server or database was briefly
 * unreachable."). Retrying transient failures a couple of times with backoff
 * absorbs those blips so the page renders instead of erroring.
 *
 * Only transient conditions are retried:
 *   - a thrown connection/network error (backend unreachable), or
 *   - a 5xx response (500/502/503/504).
 * 4xx responses (incl. 401/403/404) are returned as-is for the caller to handle
 * (e.g. map 404 → notFound()), and are never retried.
 *
 * GET is the only safe default to retry (idempotent). Callers that retry a
 * non-GET must be sure the request is safe to repeat.
 */
const RETRYABLE_STATUS = new Set([500, 502, 503, 504]);

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export async function fetchWithRetry(
  input: string,
  init?: RequestInit,
  opts: { retries?: number; backoffMs?: number } = {},
): Promise<Response> {
  const retries = opts.retries ?? 2;
  const backoffMs = opts.backoffMs ?? 300;

  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(input, init);
      // Transient server error → retry (unless out of attempts); anything else
      // (2xx, 4xx) is returned to the caller untouched.
      if (RETRYABLE_STATUS.has(res.status) && attempt < retries) {
        await sleep(backoffMs * (attempt + 1));
        continue;
      }
      return res;
    } catch (err) {
      // Connection/network error (backend unreachable). Retry, else rethrow.
      lastError = err;
      if (attempt < retries) {
        await sleep(backoffMs * (attempt + 1));
        continue;
      }
      throw err;
    }
  }
  // Unreachable in practice (the loop returns or throws), but satisfies types.
  throw lastError;
}
