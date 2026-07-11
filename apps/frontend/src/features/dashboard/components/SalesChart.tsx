"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import {
    AreaChart,
    Area,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
    Legend,
} from "recharts";
import { BarChart3 } from "lucide-react";
import type { SalesChartPoint, TeamSalesMember } from "@/features/dashboard/services/dashboardService";
import { useMounted } from "@/hooks/use-mounted";

const formatCurrency = (v: number) => {
    if (v >= 10_000_000) return `₹ ${(v / 10_000_000).toFixed(1)}Cr`;
    if (v >= 100_000) return `₹ ${(v / 100_000).toFixed(1)}L`;
    if (v >= 1_000) return `₹ ${(v / 1_000).toFixed(1)}K`;
    return `₹ ${v}`;
};

/* eslint-disable @typescript-eslint/no-explicit-any */
const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || payload.length === 0) return null;
    return (
        <div className="rounded-xl border bg-popover px-4 py-3 shadow-xl">
            <p className="mb-1.5 text-xs font-semibold text-muted-foreground">{label}</p>
            {payload.map((entry: any, idx: number) => (
                <p key={idx} className="text-sm font-semibold text-foreground">
                    <span
                        className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full align-middle"
                        style={{ backgroundColor: entry.color }}
                    />
                    {entry.name}: {formatCurrency(Number(entry.value || 0))}
                </p>
            ))}
        </div>
    );
};

const EmptyChart = ({ message }: { message: string }) => (
    <div className="flex h-[280px] flex-col items-center justify-center gap-3">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted">
            <BarChart3 className="h-8 w-8 text-muted-foreground" />
        </div>
        <p className="text-sm font-semibold text-muted-foreground">{message}</p>
    </div>
);

export function SalesChart({
    data,
    closedAmount = 0,
    openAmount = 0,
    target = 0,
    teamMembers,
}: {
    data?: SalesChartPoint[];
    closedAmount?: number;
    openAmount?: number;
    target?: number;
    /** When provided, a "Team Sales" tab shows each salesperson's closed vs
     *  open amounts (legacy-CRM semantics). "My Sales" stays the cumulative
     *  month-vs-month view of everything the viewer can see. Omit for
     *  single-scope charts (BD panel). */
    teamMembers?: TeamSalesMember[];
}) {
    const [activeTab, setActiveTab] = useState<"my" | "team">("my");
    const mounted = useMounted();
    const chartData = data ?? [];
    const hasTeamTab = teamMembers !== undefined;

    // Month labels derived from the current date so the chart always reflects
    // the live "this month" vs "last month" comparison and rolls over on its
    // own when the month changes — no hardcoded month names.
    const now = new Date();
    const thisMonthLabel = now.toLocaleString("en-US", { month: "long", year: "numeric" });
    const lastMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const lastMonthLabel = lastMonthDate.toLocaleString("en-US", { month: "long", year: "numeric" });

    return (
        <div className="rounded-lg border bg-card p-5 shadow-sm">
            {/* Header — real totals for the viewer's whole visible scope; the
                chips double as the series legend on the Team tab. */}
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-6">
                    <div className="flex items-center gap-2">
                        <span className="h-3 w-3 rounded-full" style={{ backgroundColor: "var(--chart-1)" }} />
                        <span className="text-sm font-semibold text-foreground">
                            Closed {formatCurrency(closedAmount)}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="h-3 w-3 rounded-full" style={{ backgroundColor: "var(--chart-2)" }} />
                        <span className="text-sm font-semibold text-foreground">
                            Open {formatCurrency(openAmount)}
                        </span>
                    </div>
                    {target > 0 && (
                        <div className="flex items-center gap-2">
                            <span className="h-3 w-3 rounded-full bg-muted-foreground" />
                            <span className="text-sm font-semibold text-muted-foreground">
                                Target {formatCurrency(target)}
                            </span>
                        </div>
                    )}
                </div>
                {hasTeamTab && (
                    <div className="flex rounded-full border bg-muted/40 p-1">
                        <button
                            type="button"
                            onClick={() => setActiveTab("my")}
                            className={cn(
                                "rounded-full px-5 py-1.5 text-sm font-bold transition-all duration-300",
                                activeTab === "my"
                                    ? "bg-card text-primary shadow-sm ring-1 ring-border"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            My Sales
                        </button>
                        <button
                            type="button"
                            onClick={() => setActiveTab("team")}
                            className={cn(
                                "rounded-full px-5 py-1.5 text-sm font-bold transition-all duration-300",
                                activeTab === "team"
                                    ? "bg-card text-primary shadow-sm ring-1 ring-border"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            Team Sales
                        </button>
                    </div>
                )}
            </div>

            {activeTab === "team" && hasTeamTab ? (
                /* Team Sales — each salesperson's closed vs open amounts */
                teamMembers.length === 0 ? (
                    <EmptyChart message="No team members with sales data yet" />
                ) : (
                    <div className="h-[340px] w-full">
                        {mounted && (
                        <ResponsiveContainer width="100%" height={340} minWidth={0}>
                            <BarChart
                                data={teamMembers.map((m) => ({
                                    name: m.name,
                                    Closed: m.closed,
                                    Open: m.open,
                                }))}
                                margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                                barGap={2}
                            >
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                                <XAxis
                                    dataKey="name"
                                    tick={{ fontSize: 11, fontWeight: 600, fill: "var(--muted-foreground)" }}
                                    interval={0}
                                    angle={-45}
                                    textAnchor="end"
                                    height={90}
                                    axisLine={false}
                                    tickLine={false}
                                />
                                <YAxis
                                    tick={{ fontSize: 12, fontWeight: 600, fill: "var(--muted-foreground)" }}
                                    tickFormatter={(v) => formatCurrency(v)}
                                    axisLine={false}
                                    tickLine={false}
                                />
                                <Tooltip content={<CustomTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.35 }} />
                                <Legend
                                    verticalAlign="top"
                                    height={32}
                                    iconType="circle"
                                    iconSize={8}
                                    wrapperStyle={{ fontSize: 12, fontWeight: 600 }}
                                />
                                <Bar dataKey="Closed" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={18} />
                                <Bar dataKey="Open" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={18} />
                            </BarChart>
                        </ResponsiveContainer>
                        )}
                    </div>
                )
            ) : chartData.length === 0 ? (
                <EmptyChart message="No chart data available yet" />
            ) : (
                /* My Sales — cumulative month-vs-month over the visible scope */
                <div className="h-[300px] w-full">
                    {mounted && (
                    <ResponsiveContainer width="100%" height={300} minWidth={0}>
                        <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                            <defs>
                                <linearGradient id="gradientLastMonth" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.3} />
                                    <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
                                </linearGradient>
                                <linearGradient id="gradientThisMonth" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="var(--chart-2)" stopOpacity={0.3} />
                                    <stop offset="100%" stopColor="var(--chart-2)" stopOpacity={0.02} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                            <XAxis
                                dataKey="day"
                                tick={{ fontSize: 12, fontWeight: 600, fill: "var(--muted-foreground)" }}
                                tickFormatter={(d) => `${d}`}
                                axisLine={false}
                                tickLine={false}
                                dy={10}
                            />
                            <YAxis
                                tick={{ fontSize: 12, fontWeight: 600, fill: "var(--muted-foreground)" }}
                                tickFormatter={(v) => formatCurrency(v)}
                                axisLine={false}
                                tickLine={false}
                            />
                            <Tooltip content={<CustomTooltip />} />
                            <Legend
                                verticalAlign="top"
                                height={32}
                                iconType="plainline"
                                wrapperStyle={{ fontSize: 12, fontWeight: 600 }}
                            />
                            {/* Real monthly revenue target for the visible scope —
                                hidden entirely when no target is configured. */}
                            {target > 0 && (
                                <ReferenceLine
                                    y={target}
                                    stroke="var(--muted-foreground)"
                                    strokeDasharray="4 4"
                                    label={{
                                        value: "Target",
                                        position: "insideTopRight",
                                        fill: "var(--muted-foreground)",
                                        fontSize: 11,
                                        fontWeight: 600,
                                    }}
                                />
                            )}
                            <Area
                                type="monotone"
                                dataKey="sale_last_month"
                                name={lastMonthLabel}
                                stroke="var(--chart-1)"
                                fill="url(#gradientLastMonth)"
                                strokeWidth={2.5}
                                dot={false}
                                activeDot={{ r: 5, fill: "var(--chart-1)", strokeWidth: 2, stroke: "var(--card)" }}
                            />
                            <Area
                                type="monotone"
                                dataKey="sale_this_month"
                                name={thisMonthLabel}
                                stroke="var(--chart-2)"
                                fill="url(#gradientThisMonth)"
                                strokeWidth={2.5}
                                dot={false}
                                activeDot={{ r: 5, fill: "var(--chart-2)", strokeWidth: 2, stroke: "var(--card)" }}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                    )}
                </div>
            )}
        </div>
    );
}
