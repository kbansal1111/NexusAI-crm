"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import * as z from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "next-auth/react";
import { usePicklist } from "@/hooks/use-picklist";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
    Form,
    FormControl,
    FormDescription,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { PhoneInput } from "@/components/ui/phone-input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { contactsService } from "@/lib/api/services/contacts.service";
import { ErrorHandler, ErrorType } from "@/lib/error-handler";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { useUploadFile } from "@/features/files/api/use-files";
import { MapPin, Paperclip, User, X } from "lucide-react";
import { FormSectionHeader, FormFooter, FORM_SHELL_CLASS } from "@/components/shared/form-section";

const contactFormSchema = z.object({
    salutation: z.string().optional(),
    first_name: z.string().max(100).optional(),
    last_name: z.string().min(2, {
        message: "Last name must be at least 2 characters.",
    }).max(100),
    email: z.string().min(1, { message: "Email is required." }).email({ message: "Invalid email address." }),
    phone: z.string().optional().or(z.literal("")).refine(val => !val || /^\+?\d{1,4}\s\d{10}$/.test(val), {
        message: "Please select a country code and enter exactly a 10-digit number.",
    }),
    mobile: z.string().min(1, { message: "Mobile is required." }).refine(val => !val || /^\+?\d{1,4}\s\d{10}$/.test(val), {
        message: "Please select a country code and enter exactly a 10-digit number.",
    }),
    title: z.string().optional(),
    account_id: z.string().min(1, { message: "Account is required." }),
    owner_id: z.string().optional(),
    // Mailing address
    mailing_street: z.string().optional(),
    mailing_city: z.string().optional(),
    mailing_state: z.string().optional(),
    mailing_zip: z.string().optional().or(z.literal("")).refine(val => !val || /^[A-Za-z0-9\s-]{3,10}$/.test(val), {
        message: "Invalid Zip/Postal code format.",
    }),
    mailing_country: z.string().optional(),
});

type ContactFormValues = z.infer<typeof contactFormSchema>;

const defaultValues: Partial<ContactFormValues> = {
    salutation: "",
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
    mobile: "",
    title: "",
    account_id: "",
    owner_id: "",
    mailing_street: "",
    mailing_city: "",
    mailing_state: "",
    mailing_zip: "",
    mailing_country: "",
};

/** The contact as it was just saved — lets a caller select it straight away. */
export interface SavedContact {
    id: string;
    first_name?: string;
    last_name?: string;
    full_name?: string;
}

interface ContactFormProps {
    initialData?: ContactFormValues & { owner_name?: string; owner?: { name?: string } };
    id?: string;
    /** Name of the current account (for the info banner) */
    initialAccountName?: string;
    /**
     * Pins the contact to one account and renders the picker read-only. Used
     * when the account is already decided by the calling flow — creating a
     * contact from inside the Create Opportunity form, where picking a
     * different account here would silently break the opportunity's link.
     */
    lockedAccount?: { id: string; name: string };
    onSuccess?: (saved?: SavedContact) => void;
    onCancel?: () => void;
    isDrawer?: boolean;
}

export function ContactForm({ initialData, id, initialAccountName, lockedAccount, onSuccess, onCancel, isDrawer = false }: ContactFormProps) {
    const router = useRouter();
    const { data: session } = useSession();
    const [isLoading, setIsLoading] = useState(false);
    const [accounts, setAccounts] = useState<{ id: string, name: string, website?: string }[]>([]);
    const { items: salutations } = usePicklist("salutation");

    // Track original account_id to detect changes
    const originalAccountId = useRef(initialData?.account_id ?? "");

    // Coerce null/undefined from the loaded contact to "" so inputs stay
    // controlled (React warns when an input's `value` is null).
    const sanitizedInitial = Object.fromEntries(
        Object.entries(initialData || {}).map(([k, v]) => [k, v ?? ""])
    );

    const form = useForm<ContactFormValues>({
        resolver: zodResolver(contactFormSchema),
        defaultValues: {
            ...defaultValues,
            ...sanitizedInitial,
            ...(lockedAccount ? { account_id: lockedAccount.id } : {}),
        },
    });

    // Watch account_id to show info banner
    const watchedAccountId = form.watch("account_id");
    const accountChanged = !!id && watchedAccountId !== originalAccountId.current;

    // Resolve display name of the new account for the banner
    const newAccountName = accounts.find(a => a.id === watchedAccountId)?.name;

    useEffect(() => {
        const fetchMetaData = async () => {
            try {
                const data = await contactsService.getFormData();
                setAccounts(data.accounts || []);
            } catch (err) {
                console.error("Error fetching contact form metadata", err);
            }
        };
        fetchMetaData();
    }, []);

    const handleBackendErrors = (error: any) => {
        if (error.type === ErrorType.VALIDATION && error.details?.detail) {
            const details = error.details.detail;
            details.forEach((err: any) => {
                const field = err.loc[err.loc.length - 1];
                form.setError(field as any, {
                    type: "manual",
                    message: err.msg,
                });
            });
            return true;
        }
        return false;
    };

    // Attachment (single file) — uploaded after the contact is saved, then
    // linked via fileable_type="Contact" (shows in the details Files tab).
    const uploadFile = useUploadFile();
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    async function onSubmit(data: ContactFormValues) {
        setIsLoading(true);
        const startTime = Date.now();
        let isSuccess = false;
        try {
            await ErrorHandler.withErrorHandling(async () => {
                try {
                    let savedContact;
                    if (id) {
                        savedContact = await contactsService.updateContact(id, data);
                        toast.success("Contact updated successfully");
                    } else {
                        savedContact = await contactsService.createContact(data as any);
                        toast.success("Contact created successfully");
                    }

                    // Upload the attached file (if any) and link it to the contact.
                    const savedContactId = savedContact?.id || id;
                    if (selectedFile && savedContactId) {
                        try {
                            await uploadFile.mutateAsync({
                                file: selectedFile,
                                fileable_type: "Contact",
                                fileable_id: savedContactId,
                            });
                            setSelectedFile(null);
                            if (fileInputRef.current) fileInputRef.current.value = "";
                        } catch (uploadErr) {
                            console.error("Attachment upload failed", uploadErr);
                            toast.error("Contact saved, but the attachment failed to upload.");
                        }
                    }
                    isSuccess = true;
                    
                    const elapsedTime = Date.now() - startTime;
                    if (elapsedTime < 2500) {
                        await new Promise(r => setTimeout(r, 2500 - elapsedTime));
                    }
                    
                    if (onSuccess) {
                        onSuccess(savedContact as SavedContact | undefined);
                    } else {
                        router.push("/contacts");
                        router.refresh();
                    }
                } catch (error: any) {
                    const mapped = handleBackendErrors(ErrorHandler.parseError(error, "Failed to save contact"));
                    if (!mapped) throw error;
                }
            }, "Failed to save contact");
        } catch (error) {
            // Error is already handled
        } finally {
            if (!isSuccess) {
                const elapsedTime = Date.now() - startTime;
                if (elapsedTime < 2500) {
                    await new Promise(r => setTimeout(r, 2500 - elapsedTime));
                }
                setIsLoading(false);
            }
        }
    }

    return (
        <Form {...form}>
            <form
                onSubmit={form.handleSubmit(onSubmit)}
                className={cn("space-y-5", FORM_SHELL_CLASS)}
            >
                <div>
                    <FormSectionHeader icon={User} title="Contact Information" />
                    <div className="grid gap-3 md:grid-cols-2">
                        <FormField
                            control={form.control}
                            name="salutation"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Salutation</FormLabel>
                                    <Select onValueChange={field.onChange} value={field.value ?? ""}>
                                        <FormControl>
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select" />
                                            </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                            {salutations.map((s) => (
                                                <SelectItem key={s.id} value={s.name}>{s.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        {/* Account Owner — read-only; reassignment uses Change Owner action */}
                        <div className="flex flex-col space-y-2">
                            <FormLabel>Account Owner</FormLabel>
                            <p className="h-8 rounded-md border border-border bg-muted/40 px-2 text-xs text-foreground flex items-center truncate">
                                {initialData?.owner_name
                                    || initialData?.owner?.name
                                    || session?.user?.name
                                    || "Automatically assigned to you"}
                            </p>
                        </div>

                        <FormField
                            control={form.control}
                            name="first_name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>First Name</FormLabel>
                                    <FormControl>
                                        <Input {...field} value={field.value ?? ""} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="last_name"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Last Name *</FormLabel>
                                    <FormControl>
                                        <Input {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="account_id"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Account Name *</FormLabel>
                                    {lockedAccount ? (
                                        // Read-only: the account is fixed by the calling flow. Also
                                        // avoids showing a stale picker — a just-created account is
                                        // not in the `accounts` list fetched on mount.
                                        <p className="flex h-8 items-center truncate rounded-md border border-border bg-muted/40 px-2 text-xs text-foreground">
                                            {lockedAccount.name}
                                        </p>
                                    ) : (
                                        <FormControl>
                                            <SearchableSelect
                                                options={accounts.map(acc => ({ label: acc.name, value: acc.id }))}
                                                value={field.value || ""}
                                                onValueChange={field.onChange}
                                                placeholder="Search Account"
                                            />
                                        </FormControl>
                                    )}
                                    {accountChanged && (
                                        <FormDescription>
                                            <span className="flex items-start gap-1.5 mt-1.5 text-amber-600 dark:text-amber-400 text-xs leading-snug">
                                                <span>ℹ️</span>
                                                <span>
                                                    This contact will move to
                                                    {newAccountName ? ` "${newAccountName}"` : " the new account"}.
                                                    Associated opportunities will also be reassigned to
                                                    {newAccountName ? ` "${newAccountName}"` : " the new account"}.
                                                </span>
                                            </span>
                                        </FormDescription>
                                    )}
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="title"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Title</FormLabel>
                                    <FormControl>
                                        <Input {...field} value={field.value ?? ""} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="phone"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Phone</FormLabel>
                                    <FormControl>
                                        <PhoneInput {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="mobile"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Mobile *</FormLabel>
                                    <FormControl>
                                        <PhoneInput {...field} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="email"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Email *</FormLabel>
                                    <FormControl>
                                        <Input
                                            {...field}
                                        />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                    </div>
                </div>

                <div>
                    <FormSectionHeader icon={MapPin} title="Address Information" />
                    <div className="grid gap-3 md:grid-cols-2">
                        <FormField
                            control={form.control}
                            name="mailing_street"
                            render={({ field }) => (
                                <FormItem className="md:col-span-2">
                                    <FormLabel>Mailing Street</FormLabel>
                                    <FormControl>
                                        <Input {...field} value={field.value ?? ""} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="mailing_city"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>City</FormLabel>
                                    <FormControl>
                                        <Input {...field} value={field.value ?? ""} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="mailing_state"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>State</FormLabel>
                                    <FormControl>
                                        <Input {...field} value={field.value ?? ""} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="mailing_zip"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Zip / Postal Code</FormLabel>
                                    <FormControl>
                                        <Input {...field} value={field.value ?? ""} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                        <FormField
                            control={form.control}
                            name="mailing_country"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Country</FormLabel>
                                    <FormControl>
                                        <Input {...field} value={field.value ?? ""} />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />
                    </div>
                </div>

                {/* ── Section: Attachment Information ─────────────── */}
                <div>
                    <FormSectionHeader icon={Paperclip} title="Attachment Information" />
                    {selectedFile ? (
                        <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm">
                            <span className="flex min-w-0 items-center gap-2">
                                <Paperclip className="h-4 w-4 shrink-0 text-muted-foreground" />
                                <span className="truncate text-foreground">{selectedFile.name}</span>
                            </span>
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-6 px-1"
                                onClick={() => {
                                    setSelectedFile(null);
                                    if (fileInputRef.current) fileInputRef.current.value = "";
                                }}
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    ) : (
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="w-fit"
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <Paperclip className="mr-2 h-4 w-4" />
                            Add Attachment
                        </Button>
                    )}
                    <input
                        ref={fileInputRef}
                        type="file"
                        className="hidden"
                        onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
                    />
                </div>
                <FormFooter
                    isLoading={isLoading}
                    submitLabel={id ? "Update" : "Save"}
                    loadingLabel={id ? "Updating..." : "Creating..."}
                    onCancel={() => onCancel ? onCancel() : router.back()}
                    cancelLabel={isDrawer ? "Close" : "Cancel"}
                />
            </form>
        </Form>
    );
}
