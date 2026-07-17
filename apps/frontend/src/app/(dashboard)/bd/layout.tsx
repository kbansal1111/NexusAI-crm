"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { LayoutDashboard, Target, CheckSquare, Plane, Briefcase } from "lucide-react";
import { ModuleTitle } from "@/components/shared/module-title";

const TABS = [
    { label: "Dashboard", href: "/bd", icon: LayoutDashboard, exact: true },
    { label: "Opportunities", href: "/bd/opportunities", icon: Target, exact: false },
    { label: "Tasks", href: "/bd/tasks", icon: CheckSquare, exact: false },
    { label: "Departure", href: "/bd/departure", icon: Plane, exact: false },
];

export default function BDPanelLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();

    const isActive = (href: string, exact: boolean) =>
        exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);

    return (
        <div className="crm-page">
            {/* Panel header + tabs */}
            <div className="crm-surface px-4 pt-4">
                <div className="mb-3">
                    <ModuleTitle
                        icon={Briefcase}
                        title="BD Panel"
                        description="Territory-scoped pipeline, tasks, and departures."
                    />
                </div>
                <nav className="flex flex-wrap gap-1 border-b border-border">
                    {TABS.map((tab) => {
                        const active = isActive(tab.href, tab.exact);
                        const Icon = tab.icon;
                        return (
                            <Link
                                key={tab.href}
                                href={tab.href}
                                className={cn(
                                    "flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors -mb-px",
                                    active
                                        ? "border-primary text-primary"
                                        : "border-transparent text-muted-foreground hover:text-foreground hover:border-border",
                                )}
                            >
                                <Icon className="h-4 w-4" />
                                {tab.label}
                            </Link>
                        );
                    })}
                </nav>
            </div>

            {/* Active tab content */}
            <div>{children}</div>
        </div>
    );
}
