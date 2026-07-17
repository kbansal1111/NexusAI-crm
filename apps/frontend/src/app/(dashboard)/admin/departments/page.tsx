import { Network } from "lucide-react";
import { DepartmentList } from "@/features/admin/components/departments/department-list";
import { ModuleTitle } from "@/components/shared/module-title";

export default function AdminDepartmentsPage() {
    return (
        <div className="flex-1 min-w-0 w-full space-y-4 p-4 sm:p-8 pt-4 sm:pt-6">
            <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle
                    icon={Network}
                    title="Departments"
                    description="Group users into departments for routing and reporting."
                />
            </div>
            <div className="flex h-full flex-1 flex-col space-y-8">
                <DepartmentList />
            </div>
        </div>
    );
}
