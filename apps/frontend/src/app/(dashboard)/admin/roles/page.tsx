import { ShieldCheck } from "lucide-react";
import { RoleList } from "@/features/admin/components/roles/role-list";
import { GuardedCreateLink } from "@/components/permissions/guarded-create-link";
import { ModuleTitle } from "@/components/shared/module-title";

export default function AdminRolesPage() {
    return (
        <div className="flex-1 space-y-4 p-4 sm:p-8 pt-4 sm:pt-6">
            <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle
                    icon={ShieldCheck}
                    title="Role Management"
                    description="Define what each profile can see and do."
                />
                <div className="flex items-center space-x-2">
                    <GuardedCreateLink
                        resource="role"
                        href="/admin/role-management/new"
                        label="Create Role"
                    />
                </div>
            </div>
            <div className="flex h-full flex-1 flex-col space-y-8">
                <RoleList />
            </div>
        </div>
    );
}
