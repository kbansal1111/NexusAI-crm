"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface CollapsibleDetailSectionProps {
    icon: React.ReactNode;
    title: string;
    defaultOpen?: boolean;
    children: React.ReactNode;
    className?: string;
}

export function CollapsibleDetailSection({
    icon,
    title,
    defaultOpen = false,
    children,
    className,
}: CollapsibleDetailSectionProps) {
    const [isOpen, setIsOpen] = useState(defaultOpen);

    return (
        <div className={cn("overflow-hidden rounded-lg border border-border bg-card", className)}>
            {/* Header */}
            <button
                type="button"
                onClick={() => setIsOpen((prev) => !prev)}
                className="flex w-full cursor-pointer select-none items-center gap-2 border-b border-border bg-muted/40 px-4 py-3 transition-colors hover:bg-muted/60"
                suppressHydrationWarning
            >
                <ChevronRight
                    className={cn(
                        "h-4 w-4 text-primary transition-transform duration-200",
                        isOpen && "rotate-90"
                    )}
                />
                <span className="text-primary">{icon}</span>
                <span className="text-sm font-semibold text-foreground">{title}</span>
            </button>

            {/* Content — grid-rows animation composites cheaply (no max-height reflow) */}
            <div
                className={cn(
                    "grid transition-[grid-template-rows,opacity] duration-200 ease-in-out",
                    isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
                )}
            >
                <div className="min-h-0 overflow-hidden">
                    <div className="p-6">{children}</div>
                </div>
            </div>
        </div>
    );
}
