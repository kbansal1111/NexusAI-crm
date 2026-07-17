"use client";

import { ReportBuilder } from "@/features/reports/components/report-builder";
import { FileBarChart } from "lucide-react";
import { ModuleTitle } from "@/components/shared/module-title";

export default function NewReportPage() {
    return (
        <div className="crm-page">
            <div className="crm-surface flex items-center justify-between px-4 py-3">
                <ModuleTitle icon={FileBarChart} title="New Report" description="Build a new performance snapshot." />
            </div>
            <div className="crm-surface p-4">
                <ReportBuilder />
            </div>
        </div>
    );
}
