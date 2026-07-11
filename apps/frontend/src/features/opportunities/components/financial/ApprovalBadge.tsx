import type { TransactionApprovalStatus } from "@/lib/api/services/financial.service";

// ── Approval-status badge (shared by the transaction tab and the accounts queue) ─

const APPROVAL_BADGE: Record<
    TransactionApprovalStatus,
    { label: string; className: string }
> = {
    pending_verification: {
        label: "Pending verification",
        className:
            "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
    },
    verified: {
        label: "Verified",
        className:
            "bg-primary/15 text-primary dark:text-primary border-primary/30",
    },
    approved: {
        label: "Approved",
        className:
            "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
    },
    rejected: {
        label: "Rejected",
        className:
            "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30",
    },
};

export function ApprovalBadge({ status }: { status: TransactionApprovalStatus }) {
    const cfg = APPROVAL_BADGE[status] ?? APPROVAL_BADGE.approved;
    return (
        <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${cfg.className}`}
            title={cfg.label}
        >
            {cfg.label}
        </span>
    );
}
