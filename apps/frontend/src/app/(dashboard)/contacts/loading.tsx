import { LoadingTable } from "@/components/ui/loading";

// Mirrors the loaded page's crm-page/crm-surface layout so the
// skeleton → content transition causes no layout shift.
export default function ContactsLoading() {
    return (
        <div className="crm-page">
            <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h1>Contacts</h1>
                    <p className="text-sm text-muted-foreground">
                        Manage your key contacts and people.
                    </p>
                </div>
                <div className="h-9 w-32 animate-pulse rounded-md bg-muted" />
            </div>

            <div className="crm-surface overflow-hidden p-4">
                <LoadingTable rows={10} columns={6} />
            </div>
        </div>
    );
}
