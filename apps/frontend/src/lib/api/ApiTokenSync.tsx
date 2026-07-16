"use client";

import { useEffect } from "react";
import { useSession, signOut } from "next-auth/react";
import { setApiAccessToken } from "@/lib/api/client";

/**
 * Keeps the apiClient's in-memory access token in sync with the NextAuth
 * session, so the request interceptor can attach the bearer token without a
 * getSession() round-trip per request. Render once, inside <SessionProvider>.
 *
 * Also handles a failed silent refresh: when the jwt callback couldn't renew
 * the access token (refresh token expired/invalid), it flags the session with
 * `error`, and we sign the user out to the login page with an expiry notice.
 */
export function ApiTokenSync() {
    const { data: session } = useSession();
    useEffect(() => {
        if (session?.error === "RefreshAccessTokenError") {
            setApiAccessToken(null);
            // signOut()'s internal /api/auth/csrf + /api/auth/signout fetches
            // can themselves fail (auth route hiccup, backend down) — if we
            // await them for the redirect, a failure strands the user on a
            // broken page. Fire-and-forget the cookie cleanup and navigate
            // unconditionally (same pattern as the 401 interceptor in client.ts).
            signOut({ redirect: false }).catch(() => {});
            window.location.replace("/login?reason=expired");
            return;
        }
        setApiAccessToken(session?.accessToken ?? null);
    }, [session?.accessToken, session?.error]);
    return null;
}
