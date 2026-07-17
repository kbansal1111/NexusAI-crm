import DeparturePage from "@/app/(dashboard)/departure/page";

export const dynamic = "force-dynamic";

export default function BDDeparturePage() {
    return (
        <div className="pt-4">
            <DeparturePage embedded />
        </div>
    );
}
