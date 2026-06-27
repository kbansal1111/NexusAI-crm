"use client";

import { useEffect, useState, useTransition } from "react";
import * as React from "react";
import Link from "next/link";
import { Pencil, Check, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSuppliers, useUpdateSupplier } from "@/features/suppliers/api/use-suppliers";
import { suppliersService } from "@/lib/api/services/suppliers.service";
import { SupplierActions } from "./supplier-actions";
import { Supplier } from "@/features/suppliers/types";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useIndustryLabels } from "@/lib/industry-labels";
import { customFieldsService, type EntityType } from "@/lib/api/services/field-registry.service";
import { useEntityViews } from "@/features/views/useEntityViews";
import { ListViewSelector, ListViewSettings } from "@/features/views/ListViewMenu";
import { ListCountHeader } from "@/features/views/ListCountHeader";
import { ListViewFilterButton } from "@/features/views/ListViewFilterButton";
import { DynamicListTable } from "@/features/views/DynamicListTable";
import { buildEntityColumns, type ViewLookups } from "@/features/views/accountColumnFactory";
import { buildLookupOptions, standardFieldByKey } from "@/features/views/accountFields";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";

// Inline-editable text cell. Renders the value (optionally as a link to the
// supplier detail) with a hover pencil; clicking it edits the single field.
function EditableSupplierCell({
    supplier,
    field,
    asLink = false,
    placeholder = "-",
}: {
    supplier: Supplier;
    field: "name" | "phone" | "email";
    asLink?: boolean;
    placeholder?: string;
}) {
    const updateSupplier = useUpdateSupplier();
    const initial = (supplier[field] as string) || "";
    const [editing, setEditing] = useState(false);
    const [value, setValue] = useState(initial);

    useEffect(() => setValue(initial), [initial]);

    const save = async () => {
        if (value === initial) {
            setEditing(false);
            return;
        }
        try {
            await updateSupplier.mutateAsync({ id: supplier.id, data: { [field]: value } });
            toast.success("Updated");
            setEditing(false);
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || "Failed to update");
        }
    };

    if (editing) {
        return (
            <div className="flex items-center gap-1">
                <Input
                    autoFocus
                    value={value}
                    disabled={updateSupplier.isPending}
                    onChange={(e) => setValue(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter") save();
                        if (e.key === "Escape") { setValue(initial); setEditing(false); }
                    }}
                    className="h-7 w-44 text-sm"
                />
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={save} disabled={updateSupplier.isPending}>
                    {updateSupplier.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3 text-green-500" />}
                </Button>
            </div>
        );
    }

    return (
        <div className="group/edit flex items-center gap-1.5">
            {asLink ? (
                <Link href={`/suppliers/${supplier.id}`} className="cursor-pointer font-medium text-primary hover:underline">
                    {initial || placeholder}
                </Link>
            ) : (
                <span>{initial || placeholder}</span>
            )}
            <button
                type="button"
                onClick={() => setEditing(true)}
                className="opacity-0 transition-opacity group-hover/edit:opacity-100"
                title="Edit"
            >
                <Pencil className="h-3 w-3 text-primary" />
            </button>
        </div>
    );
}

export function SupplierList() {
    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();
    const queryClient = useQueryClient();
    const [isPending, startTransition] = useTransition();
    const labels = useIndustryLabels();
    const entity: EntityType = "supplier";

    const page = parseInt(searchParams.get("page") || "1");
    const per_page = parseInt(searchParams.get("per_page") || "10");
    const view_id = searchParams.get("view_id") || undefined;

    const { data: response, isLoading, isError } = useSuppliers({ page, per_page, view_id });

    // Saved-view state (active view comes from the ?view_id URL param).
    const { activeView } = useEntityViews(entity);

    // Metadata for lookup columns / filter value dropdowns (owner, created-by).
    const { data: formData } = useQuery({
        queryKey: ["supplier-form-data"],
        queryFn: () => suppliersService.getFormData(),
        staleTime: 5 * 60 * 1000,
    });
    const users: { id: string; name: string }[] = formData?.users || [];

    const { data: supplierCustomFields = [] } = useQuery({
        queryKey: ["custom-fields", entity],
        queryFn: () => customFieldsService.list(entity, true),
        staleTime: 5 * 60 * 1000,
    });

    const fieldLabels = React.useMemo(() => {
        const m = new Map<string, string>();
        standardFieldByKey(entity).forEach((f, k) => m.set(k, f.label));
        supplierCustomFields.forEach((f) => m.set("additional:" + f.id, f.label || f.name));
        return m;
    }, [supplierCustomFields]);

    const supplierTypes: string[] = formData?.supplier_types || [];
    const usersMap = React.useMemo(() => new Map(users.map((u) => [u.id, u.name])), [users]);
    const viewLookups = React.useMemo<ViewLookups>(() => ({ users: usersMap }), [usersMap]);
    const lookupOptions = React.useMemo(
        () => buildLookupOptions(entity, {
            users,
            // supplier_type is stored as the type string itself → id === name.
            supplier_types: supplierTypes.map((t) => ({ id: t, name: t })),
        }),
        [users, supplierTypes],
    );

    const dynamicColumns = React.useMemo(
        () =>
            activeView?.display_columns?.length
                ? buildEntityColumns(activeView.display_columns, fieldLabels, {
                      entity,
                      openDetail: undefined,
                      lookups: viewLookups,
                  })
                : null,
        [activeView, fieldLabels, viewLookups],
    );

    const goToPage = (next: number) => {
        const params = new URLSearchParams(searchParams.toString());
        params.set("page", next.toString());
        startTransition(() => router.push(`${pathname}?${params.toString()}`));
    };

    const refresh = () => queryClient.invalidateQueries({ queryKey: ["suppliers"] });

    const suppliers = response?.suppliers || [];

    const toolbar = (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <ListCountHeader label="Suppliers" count={response?.total ?? suppliers.length}>
                <ListViewSelector entity={entity} presetLabel="All records" />
            </ListCountHeader>
            <div className="flex items-center gap-2">
                <Button variant="outline" size="icon" onClick={refresh} title="Refresh">
                    <RefreshCw className="h-4 w-4" />
                </Button>
                <ListViewFilterButton entity={entity} lookupOptions={lookupOptions} />
                <ListViewSettings
                    entity={entity}
                    lookupOptions={lookupOptions}
                    extra={
                        <DropdownMenuItem onClick={refresh}>
                            <RefreshCw className="mr-2 h-4 w-4" /> Refresh
                        </DropdownMenuItem>
                    }
                />
            </div>
        </div>
    );

    if (isLoading) {
        return (
            <div>
                {toolbar}
                <div className="p-4 text-center">Loading {labels.suppliers.toLowerCase()}...</div>
            </div>
        );
    }

    if (isError) {
        return (
            <div>
                {toolbar}
                <div className="p-4 text-center text-red-500">Error loading {labels.suppliers.toLowerCase()}</div>
            </div>
        );
    }

    return (
        <div>
            {toolbar}
            <div className={`rounded-md border transition-opacity duration-200 ${isPending ? "opacity-50 pointer-events-none" : ""}`}>
                {dynamicColumns ? (
                    <DynamicListTable
                        data={suppliers}
                        columns={dynamicColumns as any}
                        onRowClick={(row: Supplier) => router.push(`/suppliers/${row.id}`)}
                    />
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>{labels.supplier} Name</TableHead>
                                <TableHead>{labels.supplier} Type</TableHead>
                                <TableHead>Phone</TableHead>
                                <TableHead>Email</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {suppliers.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={5} className="h-24 text-center">
                                        No {labels.suppliers.toLowerCase()} found.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                suppliers.map((supplier: Supplier) => (
                                    <TableRow key={supplier.id}>
                                        <TableCell className="font-medium">
                                            <EditableSupplierCell supplier={supplier} field="name" asLink />
                                        </TableCell>
                                        <TableCell>{supplier.supplier_type || "-"}</TableCell>
                                        <TableCell>
                                            <EditableSupplierCell supplier={supplier} field="phone" />
                                        </TableCell>
                                        <TableCell>
                                            <EditableSupplierCell supplier={supplier} field="email" />
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <SupplierActions supplier={supplier} />
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                )}

                <div className="flex items-center justify-between space-x-2 border-t bg-card px-4 py-4">
                    <div className="text-sm text-muted-foreground">
                        Showing {suppliers.length} of {response?.total || 0} records
                    </div>
                    <div className="space-x-2">
                        <Button variant="outline" size="sm" onClick={() => goToPage(page - 1)} disabled={page <= 1}>
                            Previous
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => goToPage(page + 1)}
                            disabled={!response || page >= response.pages}
                        >
                            Next
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
