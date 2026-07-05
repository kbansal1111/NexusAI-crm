import { LoadingTable } from "@/components/ui/loading";

// Mirrors the loaded page's crm-page/crm-surface layout so the
// skeleton → content transition causes no layout shift.
export default function OpportunitiesLoading() {
    return (
        <div className="crm-page">
            <div className="crm-surface space-y-4 rounded-b-none border-b-0 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="h-9 w-56 animate-pulse rounded-md bg-muted" />
                    <div className="h-9 w-72 animate-pulse rounded-md bg-muted" />
                </div>
            </div>

            <div className="crm-surface overflow-hidden rounded-t-none border-t-0 p-4">
                <LoadingTable rows={10} columns={7} />
            </div>
        </div>
    );
}
