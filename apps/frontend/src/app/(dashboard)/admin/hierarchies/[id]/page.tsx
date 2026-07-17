"use client";

import { use } from "react";
import { ListTree } from "lucide-react";
import { HierarchyForm } from "@/features/admin/components/hierarchies/hierarchy-form";
import { useGetHierarchy } from "@/features/admin/api/use-hierarchies";
import { ModuleTitle } from "@/components/shared/module-title";

interface EditHierarchyPageProps {
    params: Promise<{ id: string }>;
}

export default function EditHierarchyPage({ params }: EditHierarchyPageProps) {
    const { id } = use(params);
    const { data: hierarchy, isLoading, isError } = useGetHierarchy(id);

    if (isLoading) {
        return <div className="p-8">Loading hierarchy details...</div>;
    }

    if (isError || !hierarchy) {
        return <div className="p-8 text-red-500">Error loading hierarchy or hierarchy not found.</div>;
    }

    return (
        <div className="flex-1 space-y-4 p-4 sm:p-8 pt-4 sm:pt-6">
            <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle
                    icon={ListTree}
                    title="Edit Role"
                    description="Rename this role or move it in the hierarchy."
                />
            </div>
            <div className="crm-surface p-4">
                <HierarchyForm initialData={hierarchy} />
            </div>
        </div>
    );
}
