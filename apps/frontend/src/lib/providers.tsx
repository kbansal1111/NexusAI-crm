"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionProvider } from "next-auth/react";
import { Session } from "next-auth";
import { useState } from "react";
import { ThemeProvider } from "next-themes";
import { ApiTokenSync } from "@/lib/api/ApiTokenSync";

export function Providers({ children, session }: { children: React.ReactNode, session: Session | null }) {
    const [queryClient] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 60000,
                refetchOnWindowFocus: false,
            },
        },
    }));

    // Session poll every 4 minutes (< the 5-min refresh buffer in lib/auth.ts).
    // The /api/auth/session route is the ONLY place a silently-refreshed access
    // token can be persisted into the session cookie (RSC renders can't
    // Set-Cookie), so the poll keeps the cookie fresh and SSR renders never
    // see an expired token. refetchOnWindowFocus revalidates immediately after
    // laptop sleep / long-backgrounded tabs, where timers were throttled.
    return (
        <SessionProvider session={session} refetchOnWindowFocus refetchInterval={4 * 60} refetchWhenOffline={false}>
            <ApiTokenSync />
            <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
                <QueryClientProvider client={queryClient}>
                    {children}
                </QueryClientProvider>
            </ThemeProvider>
        </SessionProvider>
    );
}
