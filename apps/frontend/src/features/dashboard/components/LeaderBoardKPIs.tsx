"use client";

import { cn } from "@/lib/utils";
import { useIndustry } from "@/lib/industry-labels";
import {
    Target,
    CalendarPlus,
    FolderOpen,
    Users,
    Building2,
    LogOut,
    Plane,
    IndianRupee,
    Briefcase,
    Trophy,
    Gift,
    LayoutDashboard,
} from "lucide-react";
import { ModuleTitle } from "@/components/shared/module-title";
import type { LeaderBoardKPIs as LeaderBoardKPIsType } from "@/features/dashboard/services/dashboardService";
import { formatCurrency } from "@/lib/format";
import Link from "next/link";

const KPI_CARDS: {
    key: keyof LeaderBoardKPIsType;
    label: string;
    gradient: string;
    iconBg: string;
    icon: React.ReactNode;
    format?: "currency";
    href: string;
}[] = [
    {
        key: "total_opportunities",
        label: "Total Opportunities",
        gradient: "from-violet-500 to-purple-600",
        iconBg: "bg-violet-500/12 text-violet-600 dark:text-violet-400",
        icon: <Target className="h-5 w-5" />,
        href: "/opportunities?view=all",
    },
    {
        key: "today_opportunities",
        label: "Today's Opportunities",
        gradient: "from-blue-500 to-indigo-600",
        iconBg: "bg-blue-500/12 text-blue-600 dark:text-blue-400",
        icon: <CalendarPlus className="h-5 w-5" />,
        href: "/opportunities?view=today",
    },
    {
        key: "open_opportunities",
        label: "Open Opportunities",
        gradient: "from-cyan-400 to-sky-500",
        iconBg: "bg-sky-500/12 text-sky-600 dark:text-sky-400",
        icon: <FolderOpen className="h-5 w-5" />,
        href: "/opportunities?view=today",
    },
    {
        key: "b2c_open_opportunities",
        label: "B2C Open Opportunities",
        gradient: "from-emerald-400 to-green-500",
        iconBg: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
        icon: <Users className="h-5 w-5" />,
        href: "/opportunities?view=today",
    },
    {
        key: "b2b_open_opportunities",
        label: "B2B Open Opportunities",
        gradient: "from-rose-400 to-red-500",
        iconBg: "bg-rose-500/12 text-rose-600 dark:text-rose-400",
        icon: <Building2 className="h-5 w-5" />,
        href: "/opportunities?view=today",
    },
    {
        key: "b2b_direct_open_opportunities",
        label: "Corporate Open Opportunities",
        gradient: "from-orange-400 to-amber-500",
        iconBg: "bg-orange-500/12 text-orange-600 dark:text-orange-400",
        icon: <Briefcase className="h-5 w-5" />,
        href: "/opportunities?view=today",
    },
    {
        key: "today_checkout",
        label: "Today's Checkout",
        gradient: "from-teal-400 to-emerald-500",
        iconBg: "bg-teal-500/12 text-teal-600 dark:text-teal-400",
        icon: <LogOut className="h-5 w-5" />,
        href: "/opportunities?view=today",
    },
    {
        key: "tomorrow_departures",
        label: "Tomorrow's Departures",
        gradient: "from-indigo-400 to-blue-500",
        iconBg: "bg-indigo-500/12 text-indigo-600 dark:text-indigo-400",
        icon: <Plane className="h-5 w-5" />,
        href: "/opportunities?view=today",
    },
    {
        key: "today_revenue",
        label: "Today's Revenue",
        gradient: "from-amber-400 to-orange-500",
        iconBg: "bg-amber-500/12 text-amber-600 dark:text-amber-400",
        icon: <IndianRupee className="h-5 w-5" />,
        format: "currency",
        href: "/opportunities?view=today",
    },
];

export function LeaderBoardKPIs({ kpis }: { kpis: LeaderBoardKPIsType }) {
    const industry = useIndustry();
    
    // Filter out travel-specific KPIs for non-travel industries
    const activeCards = KPI_CARDS.filter(card => {
        if (industry !== "travel") {
            if (card.key === "today_checkout" || card.key === "tomorrow_departures") {
                return false;
            }
        }
        return true;
    });

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <ModuleTitle icon={LayoutDashboard} title="Dashboard" />
                <div className="flex items-center gap-2">
                    <Link
                        href="/dashboard/leaderboard"
                        className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3.5 py-1.5 text-xs font-semibold text-primary shadow-sm transition-all hover:border-primary/40 hover:bg-primary/15 hover:shadow"
                    >
                        <Trophy className="h-3.5 w-3.5" />
                        Leader Board
                    </Link>
                    <Link
                        href="/dashboard/incentive"
                        className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3.5 py-1.5 text-xs font-semibold text-primary shadow-sm transition-all hover:border-primary/40 hover:bg-primary/15 hover:shadow"
                    >
                        <Gift className="h-3.5 w-3.5" />
                        Incentives
                    </Link>
                </div>
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-8">
                {activeCards.map(({ key, label, gradient, iconBg, icon, format, href }) => {
                    const raw = kpis[key] ?? 0;
                    const value = Number(raw);
                    const display =
                        format === "currency"
                            ? formatCurrency(value)
                            : value.toLocaleString("en-IN");
                    return (
                        <Link
                            href={href}
                            key={key}
                            className="group relative overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-300 hover:shadow-md hover:-translate-y-0.5 block"
                        >
                            {/* Gradient accent bar */}
                            <div
                                className={cn(
                                    "absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r",
                                    gradient
                                )}
                            />

                            <div className="p-4 pt-5">
                                {/* Icon */}
                                <div
                                    className={cn(
                                        "mb-3 flex h-10 w-10 items-center justify-center rounded-xl transition-transform duration-300 group-hover:scale-110",
                                        iconBg
                                    )}
                                >
                                    {icon}
                                </div>

                                {/* Label */}
                                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground transition-colors group-hover:text-foreground">
                                    {label}
                                </div>

                                {/* Value */}
                                <div
                                    className={cn("font-display text-2xl font-bold tracking-tight md:text-3xl text-foreground tabular-nums")}
                                >
                                    {display}
                                </div>
                            </div>
                        </Link>
                    );
                })}
            </div>
        </div>
    );
}
