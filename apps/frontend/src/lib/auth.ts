import { NextAuthOptions } from "next-auth";
import type { JWT } from "next-auth/jwt";
import CredentialsProvider from "next-auth/providers/credentials";
import { getApiBaseUrlNoSlash } from "@/lib/env";
import { logger } from "@/lib/logger";
import { compressPermissions, decompressPermissions } from "@/lib/permissions-compression";
import { fetchWithRetry } from "@/lib/server-fetch";

// Fallback access-token lifetime if the JWT exp can't be decoded. Kept well
// under the 30-day refresh-token / session lifetime so refresh still fires.
// Mirrors the backend ACCESS_TOKEN_EXPIRE_MINUTES (1h) — the real expiry is
// read from the token's exp claim; this is only a decode-failure safety net.
const ACCESS_TOKEN_FALLBACK_MS = 60 * 60 * 1000; // 1 hour

// Refresh the access token once it has less than this long to live. Must be
// comfortably larger than the SessionProvider refetchInterval (4 min, see
// providers.tsx) so the client-side session poll — the only place a refreshed
// token can be PERSISTED back into the cookie (RSC renders can't Set-Cookie) —
// always lands inside the refresh window before the token actually expires.
const REFRESH_BUFFER_MS = 5 * 60 * 1000; // 5 minutes

// After a transient refresh failure (backend blip / rate limit), don't retry
// on every jwt callback — getServerSession runs in the layout AND page of every
// SSR render, so an unthrottled retry loop hammers a struggling backend.
const REFRESH_FAILURE_COOLDOWN_MS = 20 * 1000;

/** Decode a JWT's `exp` claim (seconds) into epoch ms, without verifying it. */
function decodeJwtExpiryMs(jwt?: string): number | null {
    if (!jwt) return null;
    try {
        const payload = jwt.split(".")[1];
        if (!payload) return null;
        const json = Buffer.from(payload.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");
        const { exp } = JSON.parse(json);
        return typeof exp === "number" ? exp * 1000 : null;
    } catch {
        return null;
    }
}

// ── Silent access-token refresh ─────────────────────────────────────────────
//
// Failure taxonomy (this distinction is what keeps users logged in):
//   DEFINITIVE — the backend judged the refresh token itself invalid/expired
//     (400/401/403/422). The session is truly dead: flag
//     `RefreshAccessTokenError` so ApiTokenSync/middleware bounce the user to
//     login.
//   TRANSIENT — anything else: network error, 5xx after retries, 429 rate
//     limit. The refresh token is still perfectly valid; return the token
//     UNCHANGED (no error flag) so the next jwt callback simply tries again.
//     Flagging these used to hard-logout users on every backend blip or rate
//     limit — the "asks me to login again and again" bug.
const DEFINITIVE_REFRESH_STATUS = new Set([400, 401, 403, 422]);

type RefreshResult =
    | { ok: true; accessToken: string; refreshToken?: string }
    | { ok: false; definitive: boolean; reason: string };

// getServerSession runs in the root layout AND the page of every SSR render,
// and the client session endpoint can fire concurrently with it — without
// dedup a single navigation at expiry stampedes the backend /auth/refresh
// endpoint. One in-flight backend call is shared per refresh token.
const inflightRefreshes = new Map<string, Promise<RefreshResult>>();
// refreshToken → epoch ms of the last transient failure (cooldown gate).
const refreshFailureAt = new Map<string, number>();

async function requestNewAccessToken(refreshToken: string): Promise<RefreshResult> {
    try {
        const baseUrl = getApiBaseUrlNoSlash().replace(/\/api\/v1$/, "");
        // fetchWithRetry absorbs 5xx/connection blips; 4xx is returned as-is.
        const res = await fetchWithRetry(`${baseUrl}/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });
        const data = await res.json().catch(() => ({} as Record<string, unknown>));
        if (res.ok && typeof data.access_token === "string") {
            return {
                ok: true,
                accessToken: data.access_token,
                // Backend doesn't rotate refresh tokens today, but honor a
                // rotated one if it ever starts to — otherwise rotation would
                // silently break every session at the first refresh.
                refreshToken: typeof data.refresh_token === "string" ? data.refresh_token : undefined,
            };
        }
        return {
            ok: false,
            definitive: DEFINITIVE_REFRESH_STATUS.has(res.status),
            reason: `Refresh failed (${res.status}): ${(data as { detail?: string })?.detail ?? ""}`,
        };
    } catch (error) {
        // Connection/network failure after retries — backend unreachable.
        return { ok: false, definitive: false, reason: String(error) };
    }
}

async function refreshAccessToken(token: JWT): Promise<JWT> {
    const refreshToken = token.refreshToken as string | undefined;
    if (!refreshToken) {
        return { ...token, error: "RefreshAccessTokenError" };
    }

    // 30-day hard cap reached — fail hard locally, no doomed round-trip.
    const refreshExpires = decodeJwtExpiryMs(refreshToken);
    if (refreshExpires !== null && Date.now() >= refreshExpires) {
        return { ...token, error: "RefreshAccessTokenError" };
    }

    // Cooldown after a transient failure: keep serving the stale token instead
    // of re-hitting a struggling backend from every concurrent SSR render.
    const failedAt = refreshFailureAt.get(refreshToken);
    if (failedAt && Date.now() - failedAt < REFRESH_FAILURE_COOLDOWN_MS) {
        return token;
    }

    let inflight = inflightRefreshes.get(refreshToken);
    if (!inflight) {
        inflight = requestNewAccessToken(refreshToken).finally(() => {
            inflightRefreshes.delete(refreshToken);
        });
        inflightRefreshes.set(refreshToken, inflight);
    }
    const result = await inflight;

    if (result.ok) {
        refreshFailureAt.delete(refreshToken);
        return {
            ...token,
            accessToken: result.accessToken,
            refreshToken: result.refreshToken ?? refreshToken,
            accessTokenExpires: decodeJwtExpiryMs(result.accessToken) ?? Date.now() + ACCESS_TOKEN_FALLBACK_MS,
            error: undefined,
        };
    }

    if (result.definitive) {
        logger.error("Token refresh rejected — session is dead:", result.reason);
        return { ...token, error: "RefreshAccessTokenError" };
    }

    // Transient — keep the session alive; the next callback retries after the
    // cooldown. API calls may 401 against the stale token in the meantime, but
    // recover as soon as the backend does (see the 401 interceptor).
    logger.error("Token refresh transiently failed (keeping session):", result.reason);
    refreshFailureAt.set(refreshToken, Date.now());
    return token;
}

export const authOptions: NextAuthOptions = {
    secret: process.env.NEXTAUTH_SECRET,
    providers: [
        CredentialsProvider({
            name: "Credentials",
            credentials: {
                email: { label: "Email", type: "text" },
                password: { label: "Password", type: "password" },
                industry: { label: "Industry", type: "text" },
            },
            async authorize(credentials) {
                if (!credentials?.email || !credentials?.password || !credentials?.industry) return null;

                // The backend has an alias for /auth/login at the root domain.
                // We strip out the "/api/v1" suffix from the base URL so we hit the root.
                const baseUrl = getApiBaseUrlNoSlash().replace(/\/api\/v1$/, "");
                const backendUrl = `${baseUrl}/auth/login`;
                try {
                    const res = await fetch(backendUrl, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            email: credentials.email,
                            password: credentials.password,
                            industry: credentials.industry,
                        }),
                    });
                    const data = await res.json();
                    if (!res.ok) {
                        logger.error("Auth error:", res.status, data);
                        return null;
                    }

                    if (data.access_token) {
                        return {
                            id: data.user.id,
                            name: data.user.name,
                            email: data.user.email,
                            accessToken: data.access_token,
                            refreshToken: data.refresh_token,
                            role: data.user.role_ids?.[0], // Taking first role for now
                            tenantId: data.user.tenant_id,
                            permissions: data.user.permissions || [],
                            industry: data.user.industry || "travel",
                            modules: data.user.modules || {},
                        };
                    }
                    return null;
                } catch (error) {
                    // Log error in development only
                    logger.error("Auth error:", error);
                    return null;
                }
            },
        }),
    ],
    session: {
        strategy: "jwt",
        // 30 days — matches the backend refresh-token lifetime (the hard cap).
        // The 7-day access token is refreshed silently in the jwt callback, so
        // an active user stays signed in for the full 30 days. After that the
        // refresh token expires and the user must log in again.
        maxAge: 30 * 24 * 60 * 60,
    },
    callbacks: {
        async jwt({ token, user, trigger, session }) {
            // 1) Initial sign-in — seed the token + access-token expiry.
            if (user) {
                token.accessToken = user.accessToken;
                token.refreshToken = user.refreshToken;
                token.accessTokenExpires = decodeJwtExpiryMs(user.accessToken) ?? Date.now() + ACCESS_TOKEN_FALLBACK_MS;
                token.id = user.id;
                token.role = user.role;
                token.tenantId = user.tenantId;
                (token as any).permissions = compressPermissions(user.permissions);
                token.industry = user.industry;
                token.modules = user.modules;
                return token;
            }

            // 2) Client-initiated update (e.g. permission/role refresh).
            if (trigger === "update" && session?.user) {
                if (session.user.permissions) {
                    (token as any).permissions = compressPermissions(session.user.permissions);
                }
                if (session.user.role) {
                    token.role = session.user.role;
                }
                if (session.user.industry) {
                    token.industry = session.user.industry;
                }
                if (session.user.modules) {
                    token.modules = session.user.modules;
                }
            }

            // 3) Access token still comfortably valid → use as-is. The buffer
            // is generous (5 min) so the client session poll refreshes and
            // PERSISTS a new token before the old one actually expires.
            if (token.accessTokenExpires && Date.now() < token.accessTokenExpires - REFRESH_BUFFER_MS) {
                return token;
            }

            // 4) Expired/near-expiry → silent refresh with the 30-day refresh
            // token. Handles the no-refresh-token case itself (definitive
            // error → clean bounce to login instead of a zombie session).
            return await refreshAccessToken(token);
        },
        async session({ session, token }) {
            if (token && session.user) {
                session.accessToken = token.accessToken as string;
                // refreshToken intentionally not exposed to the client.
                session.error = token.error;
                session.user.id = token.id as string;
                session.user.role = token.role as string;
                (session.user as any).tenantId = token.tenantId as string;
                (session.user as any).permissions = decompressPermissions((token as any).permissions);
                (session.user as any).industry = token.industry as string;
                (session.user as any).modules = token.modules as Record<string, boolean>;
            }
            return session;
        },
    },
    pages: {
        signIn: "/login",
    },
    logger: {
        error(code, metadata) {
            if (code === "JWT_SESSION_ERROR") {
                // NextAuth uses console.error by default, which triggers the Next.js error overlay.
                // We log it as a warning instead to prevent the dev overlay from crashing the screen.
                console.warn(`[NextAuth] Session invalid or expired (decryption failed)`);
            } else {
                console.error(`[NextAuth] ${code}`, metadata);
            }
        },
        warn(code) {
            console.warn(`[NextAuth] ${code}`);
        },
        debug(code, metadata) {
            console.debug(`[NextAuth] ${code}`, metadata);
        }
    }
};
