"use client";

import * as React from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ChevronDown,
  Settings,
  Plus,
  Pencil,
  Share2,
  Filter,
  Columns3,
  Trash2,
  Pin,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  entityViewsService,
  type EntityView,
} from "@/lib/api/services/entity-views.service";
import type { EntityType } from "@/lib/api/services/field-registry.service";
import { useEntityViews } from "./useEntityViews";
import { SaveViewDialog, type SaveViewMode } from "./SaveViewDialog";
import { EditListFiltersDialog } from "./EditListFiltersDialog";
import { SelectFieldsDialog } from "./SelectFieldsDialog";
import { LIST_QUERY_KEY } from "./ListViewFilterButton";
import type { OptionList } from "./accountFields";

export interface ViewPreset {
  label: string;
  value: string;
}

// Ordering for the seeded system presets (matches backend PRESET_ORDER in
// app/core/system_views.py).
const PRESET_ORDER: Record<string, number> = {
  today: 0,
  yesterday: 1,
  this_week: 2,
  this_month: 3,
};

// Special presets that stay as `?view=<key>` flags — currently just the
// ordering-based "Recently Viewed". ("WhatsApp Enquiry" for leads and "Closed
// Won"/"Closed Lost" for opportunities used to live here but are now real seeded
// views — see backend app/core/system_views.py:_EXTRA_PRESETS and
// _OPPORTUNITY_STAGE_PRESETS.)
const SPECIAL_PRESETS_BY_ENTITY: Record<string, ViewPreset[]> = {
  lead: [
    { label: "Recently Viewed", value: "recent" },
  ],
  opportunity: [
    { label: "Recently Viewed", value: "recent" },
  ],
};

// Modules that land on the "Today" preset by default (parity with prior
// behavior). Other modules default to the cleared "all records" state.
const DEFAULT_TODAY_ENTITIES = new Set<string>(["lead", "opportunity"]);

// Select a saved view (view_id) and clear any active preset (view).
function useSelectView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return React.useCallback(
    (id: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (id) params.set("view_id", id);
      else params.delete("view_id");
      params.delete("view");
      params.delete("page");
      router.push(`${pathname}?${params.toString()}`);
    },
    [router, pathname, searchParams],
  );
}

/**
 * Left-side view selector bar — uniform across every module:
 *   [ View name ▾ ]  (×)  (📌)
 * a dropdown of system presets + saved views, a clear (×) back to the default,
 * and a pin toggle that marks the active saved view as the user's default
 * (auto-loaded on the next fresh visit). The pin uses the per-user pinned API.
 */
export function ListViewSelector({
  entity,
  presetLabel = "All records",
  className,
}: {
  entity: EntityType;
  presetLabel?: string;
  className?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { views, activeView, activeViewId } = useEntityViews(entity);
  const selectView = useSelectView();

  // Seeded system presets (Today / Yesterday / …) vs the user's saved views.
  const systemViews = React.useMemo(
    () =>
      views
        .filter((v) => v.is_system)
        .sort(
          (a, b) =>
            (PRESET_ORDER[a.preset_key ?? ""] ?? 99) - (PRESET_ORDER[b.preset_key ?? ""] ?? 99),
        ),
    [views],
  );
  const savedViews = React.useMemo(() => views.filter((v) => !v.is_system), [views]);
  const specialPresets = SPECIAL_PRESETS_BY_ENTITY[entity] || [];
  const defaultSystemView = React.useMemo(
    () => systemViews.find((v) => v.is_default) || null,
    [systemViews],
  );

  const currentPreset = searchParams.get("view");
  const hasExplicit = !!(activeViewId || currentPreset);
  const selectPreset = (value: string | null) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set("view", value);
    else params.delete("view");
    params.delete("view_id");
    params.delete("page");
    router.push(`${pathname}?${params.toString()}`);
  };

  // Per-user pinned (default) view.
  const { data: pinned = [] } = useQuery({
    queryKey: ["entity-views-pinned", entity],
    queryFn: () => entityViewsService.listPinned(entity),
    staleTime: 60_000,
  });
  const pinnedView = React.useMemo(
    () => views.find((v) => pinned.some((p) => p.view_id === v.id)) || null,
    [views, pinned],
  );
  const activeIsPinned = !!(activeView && pinnedView && activeView.id === pinnedView.id);

  // One-time on fresh load: with nothing explicitly chosen, open the pinned
  // default; failing that, modules that historically land on "Today" open their
  // default system preset. A ref guards re-applying after the user clears (×).
  const applied = React.useRef(false);
  React.useEffect(() => {
    if (applied.current) return;
    if (hasExplicit) {
      applied.current = true;
      return;
    }
    if (pinnedView) {
      applied.current = true;
      selectView(pinnedView.id);
      return;
    }
    if (DEFAULT_TODAY_ENTITIES.has(entity) && defaultSystemView) {
      applied.current = true;
      selectView(defaultSystemView.id);
    }
  }, [hasExplicit, pinnedView, defaultSystemView, entity, selectView]);

  const togglePin = async () => {
    if (!activeView) {
      toast("Open a saved view to pin it as your default");
      return;
    }
    try {
      if (activeIsPinned) {
        await entityViewsService.unpin(entity, activeView.id);
      } else {
        // Single default — drop any existing pins, then pin this one.
        await Promise.all(pinned.map((p) => entityViewsService.unpin(entity, p.view_id).catch(() => {})));
        await entityViewsService.pin(entity, activeView.id);
      }
      queryClient.invalidateQueries({ queryKey: ["entity-views-pinned", entity] });
    } catch {
      toast.error("Failed to update pinned view");
    }
  };

  const activePresetLabel = specialPresets.find((p) => p.value === currentPreset)?.label;
  const buttonLabel = activeView ? activeView.name : activePresetLabel || presetLabel;

  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent",
              className,
            )}
            title="Switch list view"
          >
            <span className="max-w-[12rem] truncate">{buttonLabel}</span>
            <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-h-80 w-60 overflow-y-auto">
          <DropdownMenuLabel className="text-xs text-muted-foreground">Presets</DropdownMenuLabel>
          <DropdownMenuItem
            onClick={() => selectView(null)}
            className={!hasExplicit ? "font-semibold text-primary" : ""}
          >
            {presetLabel}
          </DropdownMenuItem>
          {systemViews.map((v) => (
            <DropdownMenuItem
              key={v.id}
              onClick={() => selectView(v.id)}
              className={v.id === activeViewId ? "font-semibold text-primary" : ""}
            >
              {v.name}
            </DropdownMenuItem>
          ))}
          {specialPresets.map((p) => (
            <DropdownMenuItem
              key={p.value}
              onClick={() => selectPreset(p.value)}
              className={!activeView && currentPreset === p.value ? "font-semibold text-primary" : ""}
            >
              {p.label}
            </DropdownMenuItem>
          ))}
          {savedViews.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs text-muted-foreground">Saved views</DropdownMenuLabel>
              {savedViews.map((v) => (
                <DropdownMenuItem
                  key={v.id}
                  onClick={() => selectView(v.id)}
                  className={v.id === activeViewId ? "font-semibold text-primary" : ""}
                >
                  {pinnedView?.id === v.id && <Pin className="mr-1.5 h-3 w-3 shrink-0 fill-current text-red-600" />}
                  <span className="truncate">{v.name}</span>
                  {v.is_public && <span className="ml-1 text-[10px] text-muted-foreground">(team)</span>}
                </DropdownMenuItem>
              ))}
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {hasExplicit && (
        <button
          type="button"
          onClick={() => selectView(null)}
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="Clear view"
          aria-label="Clear view"
        >
          <X className="h-4 w-4" />
        </button>
      )}

      <button
        type="button"
        onClick={togglePin}
        className={cn(
          "rounded p-1 hover:bg-accent",
          activeIsPinned ? "text-red-600" : "text-muted-foreground hover:text-foreground",
        )}
        title={
          activeIsPinned
            ? "Unpin default view"
            : activeView
              ? "Pin as default view"
              : "Open a saved view to pin it"
        }
        aria-label="Pin view"
      >
        <Pin className={cn("h-4 w-4", activeIsPinned && "fill-current")} />
      </button>
    </div>
  );
}

/**
 * Right-side context-aware Settings menu. On a system preset only "New" shows;
 * on a saved view the full set (New, Rename, Sharing Settings, Edit List Filters,
 * Select Fields to display, Delete) shows. `extra` injects module-specific items
 * (Refresh / Export / Import) above the view actions.
 */
export function ListViewSettings({
  entity,
  extra,
  lookupOptions,
  hideSelectFields = false,
}: {
  entity: EntityType;
  extra?: React.ReactNode;
  lookupOptions?: Record<string, OptionList>;
  /** Hide "Select Fields to display" for layouts without swappable columns (e.g. grouped/kanban). */
  hideSelectFields?: boolean;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { activeView } = useEntityViews(entity);
  const selectView = useSelectView();

  const [saveMode, setSaveMode] = React.useState<SaveViewMode | null>(null);
  const [filtersOpen, setFiltersOpen] = React.useState(false);
  const [fieldsOpen, setFieldsOpen] = React.useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["entity-views", entity] });
    // Filter/column edits keep the same view_id, so the list query key is
    // unchanged — invalidate it explicitly so results refresh without a manual
    // reload.
    const listKey = LIST_QUERY_KEY[entity];
    if (listKey) queryClient.invalidateQueries({ queryKey: [listKey] });
  };

  const onDelete = async () => {
    if (!activeView) return;
    if (!confirm(`Delete the view "${activeView.name}"?`)) return;
    try {
      await entityViewsService.deleteView(entity, activeView.id);
      toast.success("View deleted");
      invalidate();
      selectView(null);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to delete view");
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" className="flex-shrink-0">
            <Settings className="mr-1 h-4 w-4" /> Settings <ChevronDown className="ml-1 h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {extra}
          {extra && <DropdownMenuSeparator />}
          <DropdownMenuItem onClick={() => setSaveMode("new")}>
            <Plus className="mr-2 h-4 w-4" /> New
          </DropdownMenuItem>
          {activeView && (
            <>
              <DropdownMenuItem onClick={() => setSaveMode("rename")}>
                <Pencil className="mr-2 h-4 w-4" /> Rename
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSaveMode("share")}>
                <Share2 className="mr-2 h-4 w-4" /> Sharing Settings
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setFiltersOpen(true)}>
                <Filter className="mr-2 h-4 w-4" /> Edit List Filters
              </DropdownMenuItem>
              {!hideSelectFields && (
                <DropdownMenuItem onClick={() => setFieldsOpen(true)}>
                  <Columns3 className="mr-2 h-4 w-4" /> Select Fields to display
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onDelete} className="text-red-600 focus:text-red-600">
                <Trash2 className="mr-2 h-4 w-4" /> Delete
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {saveMode && (
        <SaveViewDialog
          open={!!saveMode}
          onOpenChange={(o) => !o && setSaveMode(null)}
          entity={entity}
          mode={saveMode}
          view={activeView}
          onSaved={(v) => {
            setSaveMode(null);
            invalidate();
            selectView(v.id);
          }}
        />
      )}
      {activeView && filtersOpen && (
        <EditListFiltersDialog
          open={filtersOpen}
          onOpenChange={setFiltersOpen}
          entity={entity}
          view={activeView}
          lookupOptions={lookupOptions}
          onSaved={() => {
            invalidate();
            router.refresh();
          }}
        />
      )}
      {activeView && fieldsOpen && (
        <SelectFieldsDialog
          open={fieldsOpen}
          onOpenChange={setFieldsOpen}
          entity={entity}
          view={activeView}
          onSaved={() => {
            invalidate();
            router.refresh();
          }}
        />
      )}
    </>
  );
}
