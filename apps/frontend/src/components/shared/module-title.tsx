import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Standard page heading with the module's gradient icon badge — the same
 * badge `ListCountHeader` renders on list pages and `EntityDetailHeader`
 * renders on record pages — so every page identifies its module the same way.
 *
 * Use this on pages that don't go through `ListCountHeader` (Drive, Reports,
 * Departure, Admin, Settings, …) to keep the module glyph consistent between
 * the sidebar nav, the list header, and the page title.
 */
export function ModuleTitle({
    icon: Icon,
    title,
    description,
    className,
}: {
    /** Module glyph (matches the sidebar nav icon) rendered in a gradient badge.
     * Omit when the page is embedded under another module's header (e.g. the
     * BD Panel tabs) so one screen never shows two module badges. */
    icon?: LucideIcon;
    title: string;
    description?: string;
    className?: string;
}) {
    return (
        <div className={cn("flex min-w-0 items-center gap-3", className)}>
            {Icon && (
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-chart-5 text-white shadow-sm">
                    <Icon className="h-5 w-5" />
                </div>
            )}
            <div className="min-w-0">
                <h1 className="truncate text-xl font-bold tracking-tight text-foreground md:text-2xl">
                    {title}
                </h1>
                {description && (
                    <p className="truncate text-sm text-muted-foreground">{description}</p>
                )}
            </div>
        </div>
    );
}
