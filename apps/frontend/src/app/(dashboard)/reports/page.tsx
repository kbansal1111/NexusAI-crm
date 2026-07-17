import { ReportList } from "@/features/reports/components/report-list";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { Plus, FileBarChart } from "lucide-react";
import { PermissionGate } from "@/components/permissions/PermissionGate";
import { ModuleTitle } from "@/components/shared/module-title";

export const dynamic = "force-dynamic";

export default function ReportsPage() {
    return (
        <div className="crm-page">
            <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle
                    icon={FileBarChart}
                    title="Reports"
                    description="Build and review CRM performance snapshots."
                />
                <div className="flex items-center space-x-2">
                    <PermissionGate permission="create_report">
                        <Link href="/reports/new">
                            <Button>
                                <Plus className="mr-2 h-4 w-4" /> Create Report
                            </Button>
                        </Link>
                    </PermissionGate>
                </div>
            </div>
            <div className="crm-surface flex flex-1 flex-col space-y-6 p-4">
                <ReportList />
            </div>
        </div>
    );
}
