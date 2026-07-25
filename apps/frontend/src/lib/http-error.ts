/**
 * Helpers for server-component fetch failures.
 *
 * Server components run in Node, so anything passed to console.error lands in
 * the server log. Axios errors carry the full request on them — including the
 * `Authorization: Bearer …` header — so logging the raw error object leaks a
 * live access token into the logs. Use `describeHttpError` instead.
 */

/** HTTP status from an axios error, a fetch Response-like, or undefined. */
export function getHttpStatus(error: unknown): number | undefined {
    if (!error || typeof error !== "object") return undefined;
    const e = error as { response?: { status?: number }; status?: number };
    return e.response?.status ?? e.status;
}

/** True when the record genuinely isn't there (deleted, or never existed). */
export function isNotFound(error: unknown): boolean {
    const status = getHttpStatus(error);
    return status === 404 || status === 410;
}

/**
 * Compact, token-free one-liner describing a failed request — safe to log.
 * Never include the error object itself: see the module comment above.
 */
export function describeHttpError(error: unknown): string {
    if (!error || typeof error !== "object") return String(error);
    const e = error as {
        code?: string;
        message?: string;
        config?: { method?: string; url?: string };
        response?: { status?: number; statusText?: string };
    };
    const method = e.config?.method?.toUpperCase();
    const target = [method, e.config?.url].filter(Boolean).join(" ");
    const status = e.response?.status
        ? `${e.response.status}${e.response.statusText ? ` ${e.response.statusText}` : ""}`
        : e.code ?? "no response";
    return [target, status, e.message].filter(Boolean).join(" — ");
}
