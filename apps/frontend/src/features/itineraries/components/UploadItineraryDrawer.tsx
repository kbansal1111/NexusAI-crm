"use client";

import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { FileText, Loader2, Upload, X } from "lucide-react";
import { toast } from "sonner";

import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetDescription,
    SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DestinationMultiSelect } from "@/components/industry/IndustryOpportunityFields";
import { useUploadItinerary } from "@/features/itineraries/api/useItineraries";

interface UploadItineraryDrawerProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    // When provided, the uploaded itinerary is auto-attached to this opportunity.
    opportunityId?: string;
    onUploaded?: () => void;
}

interface UploadFormValues {
    name: string;
    destinations: string; // comma-separated destination ids (DestinationMultiSelect)
}

export function UploadItineraryDrawer({ open, onOpenChange, opportunityId, onUploaded }: UploadItineraryDrawerProps) {
    const form = useForm<UploadFormValues>({ defaultValues: { name: "", destinations: "" } });
    const { register, handleSubmit, reset, watch } = form;
    // Subscribe so DestinationMultiSelect re-renders as selections change.
    const destinations = watch("destinations");

    const [file, setFile] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const uploadMutation = useUploadItinerary();

    const resetAll = () => {
        reset({ name: "", destinations: "" });
        setFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handleClose = (next: boolean) => {
        if (!next) resetAll();
        onOpenChange(next);
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selected = e.target.files?.[0] ?? null;
        if (selected && selected.type !== "application/pdf" && !selected.name.toLowerCase().endsWith(".pdf")) {
            toast.error("Only PDF files are allowed");
            e.target.value = "";
            return;
        }
        setFile(selected);
    };

    const onSubmit = async (values: UploadFormValues) => {
        const name = values.name.trim();
        const destinationIds = (values.destinations || "").split(",").map((d) => d.trim()).filter(Boolean).join(",");

        if (!name) return toast.error("Please enter an itinerary name");
        if (!destinationIds) return toast.error("Please select at least one destination");
        if (!file) return toast.error("Please choose a PDF file");

        try {
            await uploadMutation.mutateAsync({ name, destinationIds, file, opportunityId });
            toast.success("Itinerary uploaded");
            resetAll();
            onOpenChange(false);
            onUploaded?.();
        } catch (error: any) {
            const detail = error?.response?.data?.detail;
            toast.error(typeof detail === "string" ? detail : "Upload failed");
        }
    };

    return (
        <Sheet open={open} onOpenChange={handleClose}>
            <SheetContent side="right" className="w-full sm:max-w-md flex flex-col">
                <SheetHeader>
                    <SheetTitle className="flex items-center gap-2">
                        <Upload className="h-4 w-4 text-blue-500" />
                        Upload Itinerary
                    </SheetTitle>
                    <SheetDescription>
                        Upload a PDF itinerary and tag it by destination so it can be searched and attached to opportunities.
                    </SheetDescription>
                </SheetHeader>

                <form onSubmit={handleSubmit(onSubmit)} className="flex flex-1 flex-col overflow-y-auto">
                    <div className="flex-1 space-y-5 px-4">
                        <div className="space-y-2">
                            <label htmlFor="itinerary-name" className="text-sm font-medium text-foreground/90">Name <span className="text-red-500">*</span></label>
                            <Input
                                id="itinerary-name"
                                placeholder="e.g. Bali Honeymoon 5N/6D"
                                {...register("name")}
                            />
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-medium text-foreground/90">Destination(s) <span className="text-red-500">*</span></label>
                            {/* First selected destination is the primary one (drives S3 folder). */}
                            <DestinationMultiSelect form={form} fieldName="destinations" />
                            {destinations && destinations.trim() && (
                                <p className="text-xs text-muted-foreground">The first destination is treated as the primary one.</p>
                            )}
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-medium text-foreground/90">PDF file <span className="text-red-500">*</span></label>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="application/pdf,.pdf"
                                className="hidden"
                                onChange={handleFileChange}
                            />
                            {file ? (
                                <div className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                                    <span className="flex items-center gap-2 truncate">
                                        <FileText className="h-4 w-4 text-blue-500 shrink-0" />
                                        <span className="truncate">{file.name}</span>
                                    </span>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setFile(null);
                                            if (fileInputRef.current) fileInputRef.current.value = "";
                                        }}
                                        className="text-muted-foreground hover:text-foreground"
                                    >
                                        <X className="h-4 w-4" />
                                    </button>
                                </div>
                            ) : (
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="w-full"
                                    onClick={() => fileInputRef.current?.click()}
                                >
                                    <Upload className="h-4 w-4 mr-2" /> Choose PDF
                                </Button>
                            )}
                        </div>
                    </div>

                    <SheetFooter className="flex-row justify-end gap-2">
                        <Button type="button" variant="outline" onClick={() => handleClose(false)} disabled={uploadMutation.isPending}>
                            Cancel
                        </Button>
                        <Button type="submit" disabled={uploadMutation.isPending} className="bg-blue-600 hover:bg-blue-700">
                            {uploadMutation.isPending ? (
                                <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Uploading…</>
                            ) : (
                                <>Upload</>
                            )}
                        </Button>
                    </SheetFooter>
                </form>
            </SheetContent>
        </Sheet>
    );
}
