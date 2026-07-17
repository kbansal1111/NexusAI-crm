import { ListTree } from "lucide-react";
import { HierarchyList } from "@/features/admin/components/hierarchies/hierarchy-list";
import { ModuleTitle } from "@/components/shared/module-title";

export default function AdminHierarchiesPage() {
    return (
        <div className="crm-page p-4 sm:p-8 pt-4 sm:pt-6">
            <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle
                    icon={ListTree}
                    title="Role Hierarchy"
                    description="Organize roles and who reports to whom."
                />
            </div>
            <HierarchyList />
        </div>
    );
}
