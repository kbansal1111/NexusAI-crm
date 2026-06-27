"use client";

import * as React from "react";

/**
 * Standard "<LABEL> (count)" heading shown above every module's list + filters,
 * with the saved-view selector beneath it. Centralising the markup keeps the
 * record-count display identical across modules (account, lead, opportunity,
 * contact, task, supplier, …) — pass the entity's total record count.
 *
 * Place a module icon (Lightbulb / Briefcase / …) as a sibling to the LEFT of
 * this component; the label/count/selector block itself stays uniform.
 */
export function ListCountHeader({
  label,
  count,
  children,
}: {
  label: string;
  /** Total record count for the active view; falls back to 0 while loading. */
  count?: number | null;
  /** The saved-view selector (and any inline view controls). */
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-primary sm:text-xs">
        {label} ({count ?? 0})
      </div>
      <div className="flex items-center gap-1.5">{children}</div>
    </div>
  );
}
