import { ShieldCheck } from "lucide-react";
import { RoleList } from "@/features/admin/components/roles/role-list";
import { ModuleTitle } from "@/components/shared/module-title";

export default function AdminRolesPage() {
    return (
        <div className="crm-page p-4 sm:p-8 pt-4 sm:pt-6">
            <div className="crm-surface mb-4 flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle
                    icon={ShieldCheck}
                    title="Profiles & Permissions"
                    description="Define what each profile can see and do."
                />
            </div>
            <RoleList />
        </div>
    );
}
