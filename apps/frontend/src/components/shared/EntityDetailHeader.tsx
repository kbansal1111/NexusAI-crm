"use client";

import {
    Phone,
    Mail,
    User,
    Edit,
    Trash2,
    Building2,
    Calendar
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Badge } from "@/components/ui/badge";
import { ChangeOwnerDialog } from "./ChangeOwnerDialog";
import { OwnerPopover } from "./OwnerPopover";
import { useEffect, useState } from "react";
import { getSegmentBadgeClass, getSegmentLabel } from "@/lib/segments";
import { usePermissions } from "@/hooks/use-permissions";

// Map the header's entity `type` to the permission the BACKEND actually enforces.
// Person Accounts share the /accounts endpoints, so they are gated by the
// account permissions (not the vestigial *_person_account strings) — the gate
// must match the server or we'd hide a button that works / show one that 403s.
const TYPE_PERMS: Record<
    EntityDetailHeaderProps["type"],
    { edit: string; delete: string }
> = {
    "Contact": { edit: "edit_contact", delete: "delete_contact" },
    "Account": { edit: "edit_account", delete: "delete_account" },
    "Person Account": { edit: "edit_account", delete: "delete_account" },
    "Lead": { edit: "edit_lead", delete: "delete_lead" },
    "Supplier": { edit: "edit_supplier", delete: "delete_supplier" },
};

interface EntityDetailHeaderProps {
    type: "Contact" | "Account" | "Person Account" | "Lead" | "Supplier";
    customLabel?: string;
    badge?: string;
    name: string;
    id: string;
    phone?: string;
    email?: string;
    ownerName?: string;
    ownerId?: string;
    onEdit?: () => void;
    onDelete?: () => void;
    onChangeOwner?: (newOwnerId: string) => void | Promise<unknown>;
    isChangingOwner?: boolean;
}

export function EntityDetailHeader({
    type,
    customLabel,
    badge,
    name,
    id,
    phone,
    email,
    ownerName,
    ownerId,
    onEdit,
    onDelete,
    onChangeOwner,
    isChangingOwner
}: EntityDetailHeaderProps) {
    const [isOwnerModalOpen, setIsOwnerModalOpen] = useState(false);
    const { can } = usePermissions();
    const perms = TYPE_PERMS[type];
    const canEdit = can(perms.edit);
    const canDelete = can(perms.delete);

    // Optimistic owner: reflect a just-changed owner instantly, without waiting
    // for the server round-trip / router.refresh() to land. Once the parent
    // re-renders with the reconciled owner prop, this override is cleared.
    const [optimisticOwner, setOptimisticOwner] = useState<{ id?: string; name: string } | null>(null);
    useEffect(() => {
        setOptimisticOwner(null);
    }, [ownerId, ownerName]);

    const displayOwnerId = optimisticOwner?.id ?? ownerId;
    const displayOwnerName = optimisticOwner?.name ?? ownerName;

    return (
        <div className="crm-surface mb-6 overflow-hidden">
            <div className="p-6">
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                    <div className="flex items-start gap-4 min-w-0">
                        <div className="mt-1 flex h-12 w-12 items-center justify-center rounded bg-primary text-primary-foreground">
                            {type === "Contact" ? <User size={24} /> : type === "Lead" ? <User size={24} /> : <Building2 size={24} />}
                        </div>
                        <div className="min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">{customLabel || type}</span>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 min-w-0">
                                <h1 className="text-xl md:text-2xl font-semibold break-words min-w-0">{name}</h1>
                                {badge && (
                                    <Badge variant="outline" className={`ml-2 ${getSegmentBadgeClass(badge)}`}>
                                        {getSegmentLabel(badge)}
                                    </Badge>
                                )}
                                <CopyButton value={name} label="Name" className="h-6 w-6" />
                            </div>
                        </div>
                    </div>

                    <div className="flex flex-shrink-0 flex-wrap items-center gap-2">
                        {canEdit && (
                            <Button
                                variant="default"
                                onClick={onEdit}
                            >
                                <Edit className="mr-2 h-4 w-4" />
                                Edit
                            </Button>
                        )}
                        {canDelete && (
                            <Button
                                variant="destructive"
                                onClick={onDelete}
                            >
                                <Trash2 className="mr-2 h-4 w-4" />
                                Delete
                            </Button>
                        )}
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-8">
                    <div className="space-y-1">
                        <p className="text-xs font-semibold text-muted-foreground uppercase">Phone</p>
                        <div className="flex items-center gap-2">
                            {phone ? (
                                <a href={`tel:${phone}`} className="text-sm text-primary font-medium hover:underline">
                                    {phone}
                                </a>
                            ) : (
                                <span className="text-sm text-muted-foreground font-medium">No Phone</span>
                            )}
                            {phone && (
                                <CopyButton value={phone} label="Phone" className="h-4 w-4" />
                            )}
                        </div>
                    </div>
                    <div className="space-y-1">
                        <p className="text-xs font-semibold text-muted-foreground uppercase">Email</p>
                        <div className="flex items-center gap-2 overflow-hidden">
                            {email ? (
                                <a href={`mailto:${email}`} className="text-sm text-primary font-medium truncate max-w-full hover:underline">
                                    {email}
                                </a>
                            ) : (
                                <span className="text-sm text-muted-foreground font-medium">No Email</span>
                            )}
                            {email && (
                                <CopyButton value={email} label="Email" className="h-4 w-4 flex-shrink-0" />
                            )}
                        </div>
                    </div>
                    <div className="space-y-1">
                        <p className="text-xs font-semibold text-muted-foreground uppercase">{type} Owner</p>
                        <div className="flex items-center gap-2">
                            <OwnerPopover ownerId={displayOwnerId} ownerName={displayOwnerName} className="text-sm font-medium" />
                            {onChangeOwner && canEdit ? (
                                <button
                                    type="button"
                                    onClick={() => setIsOwnerModalOpen(true)}
                                    title="Change owner"
                                    className="text-primary transition-opacity hover:opacity-70"
                                >
                                    <User className="h-3.5 w-3.5" />
                                </button>
                            ) : (
                                <User className="h-3 w-3 text-primary" />
                            )}
                        </div>
                    </div>
                    <div className="space-y-1">
                        <p className="text-xs font-semibold text-muted-foreground uppercase">{type} ID</p>
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-foreground font-medium">{id?.slice(-8) || "N/A"}</span>
                        </div>
                    </div>
                </div>
            </div>

            {onChangeOwner && (
                <ChangeOwnerDialog
                    isOpen={isOwnerModalOpen}
                    onClose={() => setIsOwnerModalOpen(false)}
                    onConfirm={async (newOwnerId, newOwnerName) => {
                        // Show the new owner instantly; revert if the server rejects.
                        if (newOwnerName) setOptimisticOwner({ id: newOwnerId, name: newOwnerName });
                        setIsOwnerModalOpen(false);
                        try {
                            await onChangeOwner(newOwnerId);
                        } catch {
                            setOptimisticOwner(null);
                        }
                    }}
                    type={type}
                    isLoading={isChangingOwner}
                    currentOwnerId={displayOwnerId}
                />
            )}
        </div>
    );
}
