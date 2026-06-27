"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { EntityType } from "@/lib/api/services/field-registry.service";
import { useEntityViews } from "./useEntityViews";
import { EditListFiltersDialog } from "./EditListFiltersDialog";
import type { OptionList } from "./accountFields";

// Each module's list query is keyed by the active view_id, NOT the view's
// filter_rules content — so editing the filters of the *same* view leaves the
// cached list untouched. Invalidating the module's list key forces a refetch
// (with the new server-applied filters) instead of requiring a manual refresh.
export const LIST_QUERY_KEY: Partial<Record<EntityType, string>> = {
  lead: "leads",
  opportunity: "opportunities",
  account: "accounts",
  personal_account: "accounts", // person accounts live in the accounts collection
  contact: "contacts",
  supplier: "suppliers",
  task: "tasks",
};

/**
 * View-aware Filter button. On a system preset (no saved view) it is disabled —
 * filtering is a property of a saved view. On a saved view it opens "Edit List
 * Filters" (create the view's filters if none yet, or edit/apply existing ones).
 */
export function ListViewFilterButton({
  entity,
  lookupOptions,
}: {
  entity: EntityType;
  lookupOptions?: Record<string, OptionList>;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { activeView } = useEntityViews(entity);
  const [open, setOpen] = React.useState(false);

  const hasFilters = !!(activeView?.filter_rules && activeView.filter_rules.length);

  return (
    <>
      <Button
        variant={hasFilters ? "default" : "outline"}
        size="icon"
        className="flex-shrink-0"
        title={activeView ? "Edit list filters" : "Select a saved view to filter"}
        disabled={!activeView}
        onClick={() => activeView && setOpen(true)}
      >
        <Filter className="h-4 w-4" />
      </Button>

      {activeView && open && (
        <EditListFiltersDialog
          open={open}
          onOpenChange={setOpen}
          entity={entity}
          view={activeView}
          lookupOptions={lookupOptions}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ["entity-views", entity] });
            const listKey = LIST_QUERY_KEY[entity];
            if (listKey) queryClient.invalidateQueries({ queryKey: [listKey] });
            router.refresh();
          }}
        />
      )}
    </>
  );
}
