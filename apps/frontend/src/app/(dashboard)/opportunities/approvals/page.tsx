"use client";

import { useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Loader2, Check, CheckCheck, X, Inbox } from "lucide-react";
import { formatCurrency, formatDate } from "@/lib/format";
import { hasPermission } from "@/lib/rbac";
import {
    useTransactionApprovalQueue,
    useQueueVerifyTransaction,
    useQueueApproveTransaction,
    useQueueRejectTransaction,
} from "@/features/opportunities/api/useOpportunityFinancial";
import { ApprovalBadge } from "@/features/opportunities/components/financial/ApprovalBadge";

const FILTERS: { key: string; label: string; status?: string }[] = [
    { key: "open", label: "Open", status: undefined },
    { key: "pending", label: "Pending verification", status: "pending_verification" },
    { key: "verified", label: "Verified", status: "verified" },
    { key: "approved", label: "Approved", status: "approved" },
    { key: "rejected", label: "Rejected", status: "rejected" },
];

export default function TransactionApprovalsPage() {
    const [filter, setFilter] = useState(FILTERS[0]);
    const { data: rows = [], isLoading } = useTransactionApprovalQueue(filter.status);

    const verify = useQueueVerifyTransaction();
    const approve = useQueueApproveTransaction();
    const reject = useQueueRejectTransaction();

    const { data: session } = useSession();
    const perms = (session?.user as any)?.permissions as string[] | undefined;
    const canVerify = hasPermission(perms, "verify_opportunity_transaction");
    const canApprove = hasPermission(perms, "approve_opportunity_transaction");

    const handleReject = (opportunityId: string, txnId: string) => {
        const reason = window.prompt("Reason for rejection (optional):") ?? undefined;
        reject.mutate({ opportunityId, txnId, reason });
    };

    return (
        <div className="space-y-4">
            <div>
                <h1 className="text-xl font-semibold text-foreground">Transaction approvals</h1>
                <p className="text-sm text-muted-foreground">
                    Verify and approve opportunity amounts entered by sales.
                </p>
            </div>

            {/* Filter tabs */}
            <div className="flex flex-wrap gap-1.5">
                {FILTERS.map((f) => (
                    <button
                        key={f.key}
                        onClick={() => setFilter(f)}
                        className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                            filter.key === f.key
                                ? "bg-primary text-white"
                                : "bg-muted text-muted-foreground hover:bg-muted/70"
                        }`}
                    >
                        {f.label}
                    </button>
                ))}
            </div>

            {isLoading ? (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="h-5 w-5 animate-spin text-primary" />
                    <span className="ml-2 text-sm text-muted-foreground">Loading queue...</span>
                </div>
            ) : rows.length === 0 ? (
                <div className="crm-empty-state py-16 text-center">
                    <Inbox className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
                    <p className="text-sm font-medium text-foreground">Nothing to review</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                        No transactions in this view.
                    </p>
                </div>
            ) : (
                <div className="border border-border rounded-lg overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-muted border-b border-border">
                                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground whitespace-nowrap">Opportunity</th>
                                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground whitespace-nowrap">Owner</th>
                                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground whitespace-nowrap">Type</th>
                                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground whitespace-nowrap">Amount</th>
                                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground whitespace-nowrap">Date</th>
                                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground whitespace-nowrap">Status</th>
                                    <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground whitespace-nowrap">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((txn) => (
                                    <tr
                                        key={txn.id}
                                        className="border-b border-border last:border-b-0 hover:bg-muted/40 transition-colors"
                                    >
                                        <td className="px-4 py-3 whitespace-nowrap">
                                            <Link
                                                href={`/opportunities/${txn.opportunity_id}`}
                                                className="text-primary dark:text-primary hover:underline"
                                            >
                                                {txn.opportunity_name || "Opportunity"}
                                            </Link>
                                        </td>
                                        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                                            {txn.owner_name || "—"}
                                        </td>
                                        <td className="px-4 py-3 text-foreground whitespace-nowrap">
                                            {txn.transaction_type}
                                        </td>
                                        <td className="px-4 py-3 text-foreground whitespace-nowrap">
                                            {formatCurrency(txn.amount)}
                                        </td>
                                        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                                            {txn.transaction_date ? formatDate(txn.transaction_date) : "—"}
                                        </td>
                                        <td className="px-4 py-3 whitespace-nowrap">
                                            <ApprovalBadge status={txn.approval_status ?? "approved"} />
                                        </td>
                                        <td className="px-4 py-3 whitespace-nowrap">
                                            <div className="flex items-center gap-1.5">
                                                {canVerify && txn.approval_status === "pending_verification" && (
                                                    <button
                                                        onClick={() => verify.mutate({ opportunityId: txn.opportunity_id, txnId: txn.id })}
                                                        disabled={verify.isPending}
                                                        className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-medium text-primary dark:text-primary hover:bg-primary/15 transition-colors disabled:opacity-50"
                                                    >
                                                        <Check className="h-3 w-3" /> Verify
                                                    </button>
                                                )}
                                                {canApprove && txn.approval_status === "verified" && (
                                                    <button
                                                        onClick={() => approve.mutate({ opportunityId: txn.opportunity_id, txnId: txn.id })}
                                                        disabled={approve.isPending}
                                                        className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
                                                    >
                                                        <CheckCheck className="h-3 w-3" /> Approve
                                                    </button>
                                                )}
                                                {(txn.approval_status === "pending_verification" ||
                                                    txn.approval_status === "verified") && (
                                                    <button
                                                        onClick={() => handleReject(txn.opportunity_id, txn.id)}
                                                        disabled={reject.isPending}
                                                        className="inline-flex items-center gap-1 rounded-md border border-red-500/30 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-700 dark:text-red-300 hover:bg-red-500/20 transition-colors disabled:opacity-50"
                                                    >
                                                        <X className="h-3 w-3" /> Reject
                                                    </button>
                                                )}
                                                {(txn.approval_status === "approved" ||
                                                    txn.approval_status === "rejected") && (
                                                    <span className="text-xs text-muted-foreground">—</span>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
