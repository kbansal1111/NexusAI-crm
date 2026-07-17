import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getSession, signOut } from 'next-auth/react';
import { API_BASE_URL } from '@/lib/env';
import { toast } from 'sonner';

export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    // On the server (Next.js SSR / Cloudflare Workers) axios' default Node
    // http/https adapter is unavailable in the Workers runtime, which makes
    // every server-side request throw. Force axios to use the native `fetch`
    // adapter when there is no `window` so SSR data fetching works on the edge
    // (and on local Node SSR, which also has global fetch). The browser keeps
    // its default adapter so features like upload progress are unaffected.
    ...(typeof window === 'undefined' ? { adapter: 'fetch' as const } : {}),
});

// ── Transient-failure retry (idempotent GETs only) ──────────────────────────
// A brief backend/DB blip surfaces as a 5xx response or a connection error. On
// the server (SSR / Cloudflare Workers) that bubbles out of the data fetch and
// trips the dashboard error boundary ("Something went wrong"); on the client it
// shows a "Failed to load" state. Retrying a GET a couple of times with backoff
// absorbs those blips so the page renders. Only GETs are retried — they're
// idempotent, so a retry can never double-submit a create/update/delete.
const RETRYABLE_STATUS = new Set([500, 502, 503, 504]);
const MAX_TRANSIENT_RETRIES = 2;

function isRetryableError(error: AxiosError): boolean {
    // A caller-aborted request (e.g. autocomplete) must never be retried.
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED') return false;
    // No response object → network / DNS / connection error (backend unreachable).
    if (!error.response) return true;
    return RETRYABLE_STATUS.has(error.response.status);
}

// In-memory access token, kept in sync with the NextAuth session by the
// <ApiTokenSync> component. This lets the request interceptor attach the
// bearer token synchronously instead of awaiting getSession() — which hits
// /api/auth/session — on every single API call. Falls back to getSession()
// only when the cache is cold (e.g. first request after a hard reload).
let cachedAccessToken: string | null = null;
export function setApiAccessToken(token: string | null) {
    cachedAccessToken = token;
}

/**
 * Get auth headers for server-side requests
 */
export const getAuthHeaders = (accessToken?: string) => {
    return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
};

// Request Interceptor: Attach Token and fix path resolution
apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
    // Strip leading slash from URL to ensure it correctly appends to baseURL
    if (config.url?.startsWith('/')) {
        config.url = config.url.substring(1);
    }

    if (typeof window !== 'undefined') {
        // Fast path: use the cached token (synced from the session). Only fall
        // back to the getSession() network round-trip when the cache is cold.
        let token = cachedAccessToken;
        if (!token) {
            const session = await getSession();
            token = session?.accessToken ?? null;
            cachedAccessToken = token;
        }
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
    }
    return config;
}, (error) => {
    return Promise.reject(error);
});

// Response Interceptor: Handle 401 (expired backend token)
//
// When the token expires every in-flight API call returns 401 at once.
// isSessionExpiring gates the redirect so only one signOut + navigation
// fires regardless of how many concurrent requests fail simultaneously.
let isSessionExpiring = false;

apiClient.interceptors.response.use(
    (response) => {
        // A successful authenticated response means the token is valid — reset gate.
        if (isSessionExpiring) isSessionExpiring = false;
        return response;
    },
    async (error: AxiosError) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

        if (error.response?.status === 401 && !originalRequest._retry) {
            if (typeof window === 'undefined') {
                return Promise.reject(error);
            }

            originalRequest._retry = true;

            try {
                // Re-fetch the session. This hits /api/auth/session, which runs
                // the jwt callback server-side — i.e. it attempts (and persists)
                // a silent refresh if the access token is expired.
                const session = await getSession();

                // Definitive dead session: no session at all, or the refresh
                // was REJECTED by the backend (refresh token expired/revoked,
                // user deactivated). Only then do we log the user out.
                if (!session?.accessToken || session.error === 'RefreshAccessTokenError') {
                    cachedAccessToken = null;
                    if (!isSessionExpiring) {
                        isSessionExpiring = true;

                        // Clear the NextAuth session cookie in the background — fire-and-forget.
                        // We don't await this; the page is navigating away regardless.
                        signOut({ redirect: false }).catch(() => {});

                        // Replace the current history entry so the back button skips
                        // the expired page and doesn't loop the user back to a broken state.
                        window.location.replace('/login?reason=expired');
                    }
                    // Never-settling promise: keeps the 401 from flashing error
                    // UI while the page navigates away; GC'd on unload.
                    return new Promise(() => {});
                }

                cachedAccessToken = session.accessToken; // keep fast-path cache fresh
                const oldToken = originalRequest.headers?.Authorization;
                const newBearer = `Bearer ${session.accessToken}`;
                if (oldToken !== newBearer) {
                    if (originalRequest.headers) {
                        originalRequest.headers.Authorization = newBearer;
                    }
                    return apiClient(originalRequest);
                }

                // Same token, session alive, no error flag → the refresh
                // transiently failed (backend blip / rate limit) or the 401 has
                // another cause. Surface the error to the caller — logging the
                // user out here turned every backend hiccup into a forced
                // re-login even though the session was perfectly valid.
                return Promise.reject(error);
            } catch {
                // getSession itself failed (auth route temporarily unreachable).
                // That says nothing about the session's validity — treat as
                // transient and let the caller's error/retry handling deal with it.
                return Promise.reject(error);
            }
        }

        if (error.response?.status === 403) {
            if (typeof window !== 'undefined' && !(originalRequest as any)._suppressForbiddenToast) {
                toast.warning("Access Denied: You do not have permission for this resource.");
            }
        }

        // Retry transient failures on idempotent GETs before giving up.
        const method = (originalRequest?.method || 'get').toLowerCase();
        if (originalRequest && method === 'get' && isRetryableError(error)) {
            const cfg = originalRequest as InternalAxiosRequestConfig & { _transientRetries?: number };
            cfg._transientRetries = cfg._transientRetries ?? 0;
            if (cfg._transientRetries < MAX_TRANSIENT_RETRIES) {
                cfg._transientRetries += 1;
                await new Promise((resolve) => setTimeout(resolve, 300 * cfg._transientRetries!));
                return apiClient(cfg);
            }
        }

        return Promise.reject(error);
    }
);
