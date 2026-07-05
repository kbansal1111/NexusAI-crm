import { LoadingTable } from "@/components/ui/loading";

// Mirrors the loaded page's crm-page/crm-surface layout so the
// skeleton → content transition causes no layout shift.
export default function LeadsLoading() {
    return (
        <div className="crm-page">
            <div className="crm-surface flex flex-col gap-4 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h1>Leads</h1>
                    <p className="text-sm text-muted-foreground">
                        Track and manage your potential business opportunities.
                    </p>
                </div>
                <div className="h-9 w-32 animate-pulse rounded-md bg-muted" />
            </div>

            <div className="crm-surface overflow-hidden p-4">
                <LoadingTable rows={10} columns={8} />
            </div>
        </div>
    );
}
