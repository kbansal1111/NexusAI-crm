"use client";

import * as React from "react";
import type { LucideIcon } from "lucide-react";

/**
 * Standard "<LABEL> (count)" heading shown above every module's list + filters,
 * with the saved-view selector beneath it. Centralising the markup keeps the
 * record-count display — and the gradient module badge — identical across
 * modules (account, lead, opportunity, contact, task, supplier, …).
 *
 * Pass the module's lucide `icon` to render the same gradient avatar used in the
 * detail-page headers, so a module looks the same in its list and its record.
 */
export function ListCountHeader({
  label,
  count,
  icon: Icon,
  children,
}: {
  label: string;
  /** Total record count for the active view; falls back to 0 while loading. */
  count?: number | null;
  /** Module glyph (matches the sidebar nav icon) rendered in a gradient badge. */
  icon?: LucideIcon;
  /** The saved-view selector (and any inline view controls). */
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      {Icon && (
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-chart-5 text-white shadow-sm">
          <Icon className="h-5 w-5" />
        </div>
      )}
      <div className="flex flex-col">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-primary tabular-nums sm:text-xs">
          {label} ({count ?? 0})
        </div>
        <div className="flex items-center gap-1.5">{children}</div>
      </div>
    </div>
  );
}
