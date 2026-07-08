"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useSession } from "next-auth/react";
import { dashboardsExtraService } from "@/lib/api/services/dashboards-extra.service";
import type { PipelineStage } from "@/features/dashboard/components/PipelineChart";
import type { SalesChartPoint } from "@/features/dashboard/services/dashboardService";
import { formatCurrency } from "@/lib/format";

// Recharts is client-only and heavy; load dynamically (matches the main dashboard).
const SalesChart = dynamic(
    () => import("@/features/dashboard/components/SalesChart").then((m) => m.SalesChart),
    { ssr: false },
);
const PipelineChart = dynamic(
    () => import("@/features/dashboard/components/PipelineChart").then((m) => m.PipelineChart),
    { ssr: false },
);

export default function BDDashboardClient() {
    const { data: session } = useSession();

    const { data, isLoading, error } = useQuery({
        queryKey: ["bd", "dashboard", session?.user?.id ?? "anon"],
        queryFn: async () => {
            const [summary, revenue, stageBreakdown] = await Promise.all([
                dashboardsExtraService.bdSummary().catch(() => ({ closed: 0, open: 0, target: 0 })),
                dashboardsExtraService.bdRevenueChart().catch(() => []),
                dashboardsExtraService.bdStageBreakdown().catch(() => ({ stages: [], total_count: 0, total_value: 0 })),
            ]);
            return { summary, revenue, stageBreakdown };
        },
        staleTime: 2 * 60 * 1000,
        refetchOnWindowFocus: false,
    });

    if (isLoading) {
        return (
            <div className="grid gap-4 xl:grid-cols-3">
                <div className="xl:col-span-2 h-[360px] animate-pulse rounded-2xl bg-muted" />
                <div className="h-[360px] animate-pulse rounded-2xl bg-muted" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="crm-surface flex h-64 flex-col items-center justify-center gap-3 text-center">
                <p className="text-sm font-semibold text-foreground">Failed to load BD dashboard</p>
                <button
                    onClick={() => window.location.reload()}
                    className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90"
                >
                    Try Again
                </button>
            </div>
        );
    }

    const summary = data?.summary ?? { closed: 0, open: 0, target: 0 };
    const chartData: SalesChartPoint[] = Array.isArray(data?.revenue) ? data!.revenue : [];
    const stages: PipelineStage[] = data?.stageBreakdown?.stages ?? [];

    return (
        <div className="space-y-4 pt-4">
            {/* Target vs Closed header */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="crm-surface p-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Closed (this month)</p>
                    <p className="mt-1 text-2xl font-bold text-foreground">{formatCurrency(summary.closed)}</p>
                </div>
                <div className="crm-surface p-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Open pipeline</p>
                    <p className="mt-1 text-2xl font-bold text-foreground">{formatCurrency(summary.open)}</p>
                </div>
                <div className="crm-surface p-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Monthly target</p>
                    <p className="mt-1 text-2xl font-bold text-foreground">{formatCurrency(summary.target)}</p>
                </div>
            </div>

            {/* Monthly Sales + Sales Stages */}
            <div className="grid gap-4 lg:grid-cols-1 xl:grid-cols-3">
                <div className="xl:col-span-2">
                    <SalesChart data={chartData} closedAmount={summary.closed} openAmount={summary.open} />
                </div>
                <PipelineChart stages={stages} />
            </div>
        </div>
    );
}
