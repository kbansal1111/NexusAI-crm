"use client";

import { useQuery } from "@tanstack/react-query";
import { destinationsService } from "@/lib/api/services/destinations.service";

/**
 * Full destination list, cached and deduped across every consumer (list
 * tables, form drawers, convert dialogs). One request serves them all for
 * 10 minutes instead of each component refetching on mount.
 */
export function useAllDestinations(enabled = true) {
    return useQuery({
        queryKey: ["destinations", "all"],
        queryFn: () => destinationsService.getDestinations({ limit: 1000 }),
        staleTime: 10 * 60 * 1000,
        enabled,
    });
}
