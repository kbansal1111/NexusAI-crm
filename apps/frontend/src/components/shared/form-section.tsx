"use client";

import type { LucideIcon } from "lucide-react";

/**
 * Canonical section heading for all module create/edit forms — the Lead-form
 * look. Every drawer form uses this so sections read identically across
 * modules (same size, color, divider, and icon treatment).
 */
export function FormSectionHeader({
    icon: Icon,
    title,
}: {
    icon: LucideIcon;
    title: string;
}) {
    return (
        <div className="mb-3 flex items-center gap-2.5 border-b border-border pb-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Icon className="h-3.5 w-3.5" />
            </span>
            <h3 className="text-sm font-semibold tracking-tight text-foreground">
                {title}
            </h3>
        </div>
    );
}

/**
 * Form-root className that normalizes labels and controls to the shared
 * compact look without touching every field: 10px bold uppercase labels,
 * 32px-high inputs/selects with xs text. `!` is needed where the primitive's
 * own classes tie on specificity (select-trigger data-size height, label
 * color set inline per field in older forms).
 */
export const FORM_SHELL_CLASS = [
    "w-full",
    "[&_[data-slot=form-label]]:text-[10px]",
    "[&_[data-slot=form-label]]:font-bold",
    "[&_[data-slot=form-label]]:uppercase",
    "[&_[data-slot=form-label]]:!text-foreground/85",
    "[&_[data-slot=input]]:h-8",
    "[&_[data-slot=input]]:text-xs",
    "[&_[data-slot=input]]:bg-background",
    "[&_[data-slot=select-trigger]]:!h-8",
    "[&_[data-slot=select-trigger]]:text-xs",
    "[&_[data-slot=select-trigger]]:bg-background",
    "[&_[data-slot=textarea]]:text-xs",
    "[&_input]:text-foreground",
    "[&_textarea]:text-foreground",
    "[&_[data-slot=select-trigger]]:text-foreground",
].join(" ");

/** Body wrapper for drawer forms: same padding/rhythm as the Lead form.
 * pb-6 keeps the last field clear of the sticky Save/Close footer. */
export const FORM_BODY_CLASS = "px-5 pt-4 pb-6 space-y-5";

/** Top shadow for sticky drawer footers — makes the boundary visible when
 * form content scrolls beneath the translucent action bar. */
export const FORM_FOOTER_SHADOW = "shadow-[0_-8px_16px_-8px_rgb(0_0_0/0.18)]";

/** Two-column field grid with the shared density. */
export const FORM_GRID_CLASS = "grid gap-3 grid-cols-1 sm:grid-cols-2";
