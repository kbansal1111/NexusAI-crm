"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCw, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

// A deploy replaces the content-hashed JS chunks on Workers Assets, so a tab
// opened before the deploy 404s when it lazy-loads a route chunk. Webpack
// caches the failed import, meaning reset() can never recover — only a full
// page reload (which fetches the new HTML + chunk URLs) can.
const STALE_CHUNK_RE =
  /ChunkLoadError|Loading chunk [^ ]+ failed|Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i;

const CHUNK_RELOAD_KEY = "dashboard-chunk-reload-at";

/**
 * Dashboard-level error boundary.
 *
 * Without this, any error thrown while server-rendering a dashboard page
 * (e.g. the backend/DB being momentarily unreachable, a failed data fetch,
 * or a thrown getServerSession) bubbles past every layout and Next falls
 * through to its bare, unstyled root 404 — exactly the "This page could not
 * be found" screen users were hitting on a transient Atlas blip.
 *
 * This boundary keeps the user inside the app with a styled message and a
 * Retry that re-runs the failed render. Stale-deploy chunk errors are
 * auto-recovered with a one-shot full reload instead.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const isStaleChunk = useMemo(
    () => STALE_CHUNK_RE.test(`${error?.name ?? ""} ${error?.message ?? ""}`),
    [error]
  );
  const [reloading, setReloading] = useState(false);

  useEffect(() => {
    // Surface for debugging; the digest links to the server-side stack.
    console.error("Dashboard render error:", error);

    if (!isStaleChunk) return;
    // Auto-reload once to pick up the new deployment. The timestamp guard
    // stops a reload loop if a chunk is genuinely missing (not just stale).
    let last = 0;
    try {
      last = Number(sessionStorage.getItem(CHUNK_RELOAD_KEY) || 0);
    } catch {
      /* storage unavailable — fall through to the manual button */
    }
    if (Date.now() - last > 30_000) {
      try {
        sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()));
      } catch {
        /* ignore */
      }
      setReloading(true);
      window.location.reload();
    }
  }, [error, isStaleChunk]);

  // Chunk errors can't be fixed by reset() — retry must be a full reload.
  const retry = () => (isStaleChunk ? window.location.reload() : reset());

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertTriangle className="h-7 w-7" />
      </div>
      <div className="space-y-1.5">
        <h2 className="text-xl font-semibold">
          {isStaleChunk ? "App updated" : "Something went wrong"}
        </h2>
        <p className="max-w-md text-sm text-muted-foreground">
          {isStaleChunk
            ? reloading
              ? "A new version of the app was just deployed. Reloading…"
              : "A new version of the app was just deployed. Please reload the page to continue."
            : "We couldn't load this page. This usually means the server or database was briefly unreachable. Please try again in a moment."}
        </p>
        {(error?.digest || error?.name) && (
          <p className="text-xs text-muted-foreground/70">
            Ref: {error?.digest ?? error?.name}
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button onClick={retry} className="gap-2" disabled={reloading}>
          <RotateCw className="h-4 w-4" /> {isStaleChunk ? "Reload" : "Try again"}
        </Button>
        <Button variant="outline" asChild className="gap-2">
          <Link href="/dashboard">
            <ArrowLeft className="h-4 w-4" /> Back to dashboard
          </Link>
        </Button>
      </div>
    </div>
  );
}
