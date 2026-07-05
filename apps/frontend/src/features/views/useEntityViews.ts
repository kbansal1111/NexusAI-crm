"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  entityViewsService,
  type EntityView,
} from "@/lib/api/services/entity-views.service";
import type { EntityType } from "@/lib/api/services/field-registry.service";

/**
 * Shared saved-view state for a list module. The active view is the `view_id`
 * URL param (a saved EntityView); when absent the list is on a system preset
 * (e.g. "Recently Viewed"). React Query dedupes the fetch across the ListViewMenu
 * and the table that consumes the active view's display_columns.
 */
export function useEntityViews(entity: EntityType) {
  const searchParams = useSearchParams();
  const activeViewId = searchParams.get("view_id") || null;

  const { data: views = [], isLoading } = useQuery({
    queryKey: ["entity-views", entity],
    queryFn: () => entityViewsService.listViews(entity),
    staleTime: 60_000,
  });

  const activeView: EntityView | null =
    views.find((v) => v.id === activeViewId) || null;

  return { views, activeView, activeViewId, isLoading };
}

// Modules that land on the "Today" preset by default (parity with prior
// behavior). Other modules default to the cleared "all records" state.
export const DEFAULT_TODAY_ENTITIES = new Set<string>(["lead", "opportunity"]);

/**
 * Resolves the default list view on a fresh page load, BEFORE any rows render.
 *
 * With nothing explicitly chosen in the URL, the user's pinned view — or, for
 * modules that historically land on "Today", the default system preset — is
 * applied via `router.replace` (no history entry, so Back skips the redirect).
 *
 * `resolving` stays true until the decision lands in the URL; list pages gate
 * their data fetch + render on it so the unfiltered "all records" result never
 * flashes (and is never even requested) before the default view applies.
 *
 * Once resolved, it never flips back: clearing the view (×) keeps the page on
 * "all records" without re-triggering the redirect.
 */
export function useDefaultViewBoot(entity: EntityType) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const hasExplicit = !!(searchParams.get("view_id") || searchParams.get("view"));

  const { data: views = [], isLoading: viewsLoading } = useQuery({
    queryKey: ["entity-views", entity],
    queryFn: () => entityViewsService.listViews(entity),
    staleTime: 60_000,
  });
  const { data: pinned = [], isLoading: pinnedLoading } = useQuery({
    queryKey: ["entity-views-pinned", entity],
    queryFn: () => entityViewsService.listPinned(entity),
    staleTime: 60_000,
  });

  const pinnedView =
    views.find((v) => pinned.some((p) => p.view_id === v.id)) || null;
  const defaultSystemView = DEFAULT_TODAY_ENTITIES.has(entity)
    ? views.find((v) => v.is_system && v.is_default) || null
    : null;
  const target = pinnedView || defaultSystemView;
  const targetId = target?.id ?? null;

  const [resolved, setResolved] = React.useState(hasExplicit);

  React.useEffect(() => {
    if (resolved) return;
    if (hasExplicit) {
      setResolved(true);
      return;
    }
    if (viewsLoading || pinnedLoading) return;
    if (targetId) {
      const params = new URLSearchParams(searchParams.toString());
      params.set("view_id", targetId);
      params.delete("view");
      params.delete("page");
      router.replace(`${pathname}?${params.toString()}`);
      // Stay "resolving" until the URL update lands (hasExplicit flips true).
      return;
    }
    setResolved(true); // no pinned/default view — "all records" is correct
    // searchParams intentionally omitted: it only feeds the one-shot redirect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolved, hasExplicit, viewsLoading, pinnedLoading, targetId, router, pathname]);

  return { resolving: !resolved };
}
