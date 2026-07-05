import { LoadingTable } from "@/components/ui/loading";

// Mirrors the loaded page's crm-page/crm-surface layout so the
// skeleton → content transition causes no layout shift.
export default function AccountsLoading() {
    return (
        <div className="crm-page">
            <div className="crm-surface px-4 py-3">
                <div>
                    <h1>Accounts</h1>
                    <p className="text-sm text-muted-foreground">Manage company records, ownership, and account activity.</p>
                </div>
            </div>

            <div className="crm-surface overflow-hidden p-4">
                <LoadingTable rows={10} columns={6} />
            </div>
        </div>
    );
}
