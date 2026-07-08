import OpportunitiesPageClient from "@/app/(dashboard)/opportunities/OpportunitiesPageClient";

export const dynamic = "force-dynamic";

export default function BDOpportunitiesPage() {
    return (
        <div className="pt-4">
            <OpportunitiesPageClient />
        </div>
    );
}
