"use client";

import { useQueryClient } from "@tanstack/react-query";
import { FormDrawer } from "@/components/shared/FormDrawer";
import { ContactForm, type SavedContact } from "./ContactForm";
import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";

interface ContactFormDrawerProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    /** Optional data indicating edit mode */
    initialData?: any;
    /** Contact ID for edit mode */
    contactId?: string;
    /** Initial Account string for display logic */
    initialAccountName?: string;
    /** Pins the new contact to one account and locks the picker. */
    lockedAccount?: { id: string; name: string };
    /**
     * Fires after a successful save with the saved contact, so a parent form
     * (e.g. Create Opportunity) can select it without a round-trip.
     */
    onSaved?: (saved?: SavedContact) => void;
    /** Pass 1 when opened from inside another drawer so it stacks on top. */
    level?: number;
}

export function ContactFormDrawer({
    open,
    onOpenChange,
    initialData,
    contactId,
    initialAccountName,
    lockedAccount,
    onSaved,
    level = 0,
}: ContactFormDrawerProps) {
    const queryClient = useQueryClient();
    const router = useRouter();
    const [editData, setEditData] = useState<any>(initialData);
    const [loading, setLoading] = useState(false);
    
    useEffect(() => {
        if (!open || !contactId || editData) return;
        
        let cancelled = false;
        const fetchContact = async () => {
            setLoading(true);
            try {
                // If we didn't get initialData but have a contactId, we should ideally fetch it.
                // In the current uses, initialData is usually passed from the detail or list view.
            } catch (error) {
                console.error("Failed to load contact:", error);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        fetchContact();
        return () => { cancelled = true; };
    }, [open, contactId, editData]);

    const handleSuccess = (saved?: SavedContact) => {
        queryClient.invalidateQueries({ queryKey: ["contacts"] });
        // Might also affect account details if they show related contacts
        queryClient.invalidateQueries({ queryKey: ["accounts"] });
        onSaved?.(saved);
        // Skip the server re-render when nested inside another form: the parent
        // is still mid-edit, and whichever drawer owns the flow refreshes once
        // its own save completes.
        if (!onSaved) router.refresh();
        onOpenChange(false);
        setEditData(undefined);
    };

    const handleClose = () => {
        onOpenChange(false);
        setEditData(undefined);
    };

    const titleMode = contactId ? "Edit" : "Create";
    const title = `${titleMode} Contact${editData?.first_name ? ` — ${editData.first_name} ${editData.last_name || ""}` : ""}`;

    return (
        <FormDrawer
            open={open}
            onOpenChange={handleClose}
            title={title}
            subtitle={
                contactId
                    ? "Update the details of this contact"
                    : lockedAccount
                        ? `New contact under ${lockedAccount.name}`
                        : "Enter details for a new contact"
            }
            level={level}
        >
            {loading ? (
                <div className="flex items-center justify-center h-64">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    <span className="ml-2 text-sm text-muted-foreground">Loading form...</span>
                </div>
            ) : (
                <div className="p-5 overflow-x-hidden">
                    <ContactForm
                        key={contactId || "new"}
                        initialData={editData || initialData}
                        id={contactId}
                        initialAccountName={initialAccountName}
                        lockedAccount={lockedAccount}
                        onSuccess={handleSuccess}
                        onCancel={handleClose}
                        isDrawer
                    />
                </div>
            )}
        </FormDrawer>
    );
}
