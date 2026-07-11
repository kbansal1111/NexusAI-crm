"use client";

import { useState } from "react";
import {
    ClipboardList, Building2, Target, UserPlus, Users, Briefcase, UserRound,
    FileText, Receipt, CreditCard, ShieldCheck, UserCog, Truck, CalendarDays,
} from "lucide-react";
import { formatDateTime } from "@/lib/format";
import type { ActivityLog } from "@/features/dashboard/services/dashboardService";

// One icon per module — keys are lowercase; lookups normalize the stored
// entity_type (services log both "Task" and "task", etc.). Keep this in sync
// with the entity_type values emitted by the backend ActivityMixin callers.
const typeIcons: Record<string, React.ReactNode> = {
    task: <ClipboardList className="h-4 w-4 text-primary" />,
    account: <Briefcase className="h-4 w-4 text-emerald-500" />,
    personal_account: <UserRound className="h-4 w-4 text-emerald-500" />,
    contact: <Users className="h-4 w-4 text-sky-500" />,
    lead: <UserPlus className="h-4 w-4 text-amber-500" />,
    opportunity: <Target className="h-4 w-4 text-violet-500" />,
    opportunity_transaction: <CreditCard className="h-4 w-4 text-violet-500" />,
    payment: <CreditCard className="h-4 w-4 text-emerald-500" />,
    invoice: <Receipt className="h-4 w-4 text-cyan-600" />,
    quote: <FileText className="h-4 w-4 text-cyan-600" />,
    supplier: <Truck className="h-4 w-4 text-orange-500" />,
    event: <CalendarDays className="h-4 w-4 text-rose-500" />,
    user: <UserCog className="h-4 w-4 text-muted-foreground" />,
    user_roles: <ShieldCheck className="h-4 w-4 text-muted-foreground" />,
    role: <ShieldCheck className="h-4 w-4 text-muted-foreground" />,
};

const typeLabels: Record<string, string> = {
    personal_account: "Person Account",
    opportunity_transaction: "Transaction",
    user_roles: "User Roles",
};

function titleCase(s: string): string {
    return s
        .split(/[_\s]+/)
        .filter(Boolean)
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
}

function formatActivityTitle(action: string, entityType: string): string {
    const type = (entityType || "").toLowerCase();
    const entityLabel = typeLabels[type] || titleCase(type);
    const a = (action || "").toLowerCase();

    if (a === "create" || a === "created") return `Created ${entityLabel}`;
    if (a === "update" || a === "updated") return `Updated ${entityLabel}`;
    if (a === "delete" || a === "deleted") return `Deleted ${entityLabel}`;
    // Compound actions like "task_created" already name what happened —
    // "Task Created" reads better than "Task_created Lead".
    if (a.includes("_")) return titleCase(a);
    return `${titleCase(a)} ${entityLabel}`;
}

/** The detail line under the title. Backend descriptions often repeat the
 *  title ("Created lead: Acme") — strip that boilerplate so the stream reads
 *  "Admin User – Acme" instead of "Admin User – [Acme] Created lead: Acme". */
function formatActivityDetail(activity: ActivityLog): string {
    const desc = (activity.description || "").trim();
    const name = (activity.entity_name || "").trim();
    if (!desc) return name;
    const m = desc.match(/^(created|updated|deleted|converted)\s+[\w ]+:\s*(.+)$/i);
    if (m) return m[2];
    return desc;
}

export function UserActivities({ activities }: { activities: ActivityLog[] }) {
    const [refreshing, setRefreshing] = useState(false);

    const handleRefresh = () => {
        setRefreshing(true);
        setTimeout(() => setRefreshing(false), 600);
    };

    return (
        <div className="rounded-lg border bg-card p-4 text-card-foreground shadow-sm">
            <div className="flex items-center justify-between border-b pb-2 font-semibold text-foreground">
                <span className="text-lg tracking-tight">Recent Activity Stream</span>
                <button
                    type="button"
                    onClick={handleRefresh}
                    disabled={refreshing}
                    className="text-muted-foreground transition-colors hover:text-primary"
                    aria-label="Refresh activities"
                >
                    <svg
                        className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                        />
                    </svg>
                </button>
            </div>
            <div className="relative max-h-[320px] overflow-y-auto">
                <div className="absolute left-[11px] top-2 bottom-2 w-px bg-border" />
                <ul className="space-y-0">
                    {activities.length === 0 ? (
                        <li className="relative pl-8 pb-4 text-sm text-muted-foreground">
                            No recent activities
                        </li>
                    ) : (
                        activities.map((activity) => {
                            let dateStr = activity.created_at;
                            try {
                                dateStr = formatDateTime(activity.created_at);
                            } catch {
                                // keep original
                            }
                            return (
                                <li key={activity.id} className="relative pl-8 pb-4">
                                    <div className="absolute left-0 flex h-6 w-6 items-center justify-center rounded-full border bg-background">
                                        {typeIcons[(activity.entity_type || "").toLowerCase()] || <ClipboardList className="h-4 w-4 text-muted-foreground" />}
                                    </div>
                                    <p className="text-sm font-medium">
                                        {formatActivityTitle(activity.action, activity.entity_type)}
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        {activity.user_name} – {formatActivityDetail(activity)}
                                    </p>
                                    <p className="mt-0.5 text-xs text-muted-foreground">{dateStr}</p>
                                </li>
                            );
                        })
                    )}
                </ul>
            </div>
        </div>
    );
}
