"use client";

import * as React from "react";
import { AlertTriangle, RotateCw, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Catches render errors thrown by the form inside the drawer so a crashing
 * form never bubbles up to the page-level error boundary and blanks the whole
 * page — the list stays alive and the user can retry or just close the drawer.
 * Closing the drawer unmounts this boundary (`if (!open) return null` below),
 * so reopening always starts clean.
 */
class DrawerErrorBoundary extends React.Component<
    { children: React.ReactNode },
    { error: Error | null }
> {
    state: { error: Error | null } = { error: null };

    static getDerivedStateFromError(error: Error) {
        return { error };
    }

    componentDidCatch(error: Error) {
        console.error("Drawer form render error:", error);
    }

    render() {
        if (this.state.error) {
            return (
                <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                        <AlertTriangle className="h-6 w-6" />
                    </div>
                    <p className="text-sm font-semibold text-foreground">
                        This form ran into an error
                    </p>
                    <p className="max-w-sm text-xs text-muted-foreground">
                        Your other work on this page is unaffected. You can retry,
                        or close the drawer and try again.
                    </p>
                    <p className="text-xs text-muted-foreground/70">
                        Ref: {this.state.error.name}
                    </p>
                    <button
                        type="button"
                        onClick={() => this.setState({ error: null })}
                        className="mt-1 inline-flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium transition-colors hover:bg-accent"
                    >
                        <RotateCw className="h-3.5 w-3.5" /> Try again
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

interface FormDrawerProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    title: string;
    children: React.ReactNode;
    /** Optional subtitle under the title */
    subtitle?: string;
    /** Width class override, defaults to ~480px */
    widthClass?: string;
}

export function FormDrawer({
    open,
    onOpenChange,
    title,
    children,
    subtitle,
    widthClass = "w-[560px]",
}: FormDrawerProps) {
    // Close on Escape key
    React.useEffect(() => {
        if (!open) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                onOpenChange(false);
            }
        };
        document.addEventListener("keydown", onKeyDown);
        return () => document.removeEventListener("keydown", onKeyDown);
    }, [open, onOpenChange]);

    // Prevent body scroll when drawer is open
    React.useEffect(() => {
        if (open) {
            document.body.style.overflow = "hidden";
        } else {
            document.body.style.overflow = "";
        }
        return () => {
            document.body.style.overflow = "";
        };
    }, [open]);

    if (!open) return null;

    return (
        <>
            {/* Backdrop overlay */}
            <div
                className={cn(
                    "fixed inset-0 z-50 bg-black/20",
                    "animate-in fade-in-0 duration-300"
                )}
                onClick={() => onOpenChange(false)}
                aria-hidden="true"
            />

            {/* Drawer panel */}
            <div
                className={cn(
                    // text-left: the drawer is portaled where it's declared in the
                    // DOM (e.g. inside a `text-right` table actions cell), and
                    // text-align inherits even through `position: fixed` — without
                    // this reset, section headings/labels inherit right-alignment.
                    "fixed inset-y-0 right-0 z-50 flex flex-col text-left",
                    "bg-card shadow-2xl border-l border-border",
                    "animate-in slide-in-from-right duration-300 ease-out",
                    widthClass,
                    "max-w-[90vw]" // never wider than viewport on mobile
                )}
                role="dialog"
                aria-modal="true"
                aria-label={title}
            >
                <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-card px-5 py-4 shrink-0">
                    <div>
                        <h2 className="text-base font-semibold tracking-tight text-foreground">
                            {title}
                        </h2>
                        {subtitle && (
                            <p className="mt-0.5 text-xs text-muted-foreground">
                                {subtitle}
                            </p>
                        )}
                    </div>
                    <button
                        onClick={() => onOpenChange(false)}
                        className="rounded-md p-1.5 transition-colors hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring"
                        aria-label="Close"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>

                {/* Scrollable body */}
                <div className="flex-1 overflow-y-auto overflow-x-hidden">
                    <DrawerErrorBoundary>{children}</DrawerErrorBoundary>
                </div>
            </div>
        </>
    );
}
