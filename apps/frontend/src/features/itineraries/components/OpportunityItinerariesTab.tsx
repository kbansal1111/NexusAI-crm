"use client";

import { useEffect, useMemo, useState } from "react";
import { Search, Map, Paperclip, Upload, Download, X, Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
    useOpportunityItineraries,
    useItineraries,
    useLinkItinerary,
    useUnlinkItinerary,
} from "@/features/itineraries/api/useItineraries";
import { itinerariesService } from "@/lib/api/services/itineraries.service";
import { UploadItineraryDrawer } from "@/features/itineraries/components/UploadItineraryDrawer";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";

interface OpportunityItinerariesTabProps {
    opportunityId: string;
}

async function openPdf(fileId?: string | null) {
    if (!fileId) {
        toast.error("No PDF attached to this itinerary");
        return;
    }
    try {
        const url = await itinerariesService.getPdfUrl(fileId);
        window.open(url, "_blank", "noopener,noreferrer");
    } catch {
        toast.error("Could not open the PDF");
    }
}

export function OpportunityItinerariesTab({ opportunityId }: OpportunityItinerariesTabProps) {
    const { data: itineraries, isLoading } = useOpportunityItineraries(opportunityId);
    const [searchQuery, setSearchQuery] = useState("");
    const [uploadOpen, setUploadOpen] = useState(false);
    const [attachOpen, setAttachOpen] = useState(false);

    const linkMutation = useLinkItinerary(opportunityId);
    const unlinkMutation = useUnlinkItinerary(opportunityId);

    const linkedItins = itineraries || [];
    const linkedIds = useMemo(() => new Set(linkedItins.map((i) => i.itinerary.id)), [linkedItins]);

    const filteredLinked = linkedItins.filter((item) =>
        item.itinerary.name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const handleUnlink = async (itineraryId: string) => {
        try {
            await unlinkMutation.mutateAsync(itineraryId);
            toast.success("Itinerary removed");
        } catch {
            toast.error("Failed to remove itinerary");
        }
    };

    return (
        <div className="space-y-6">
            <div className="mb-6 flex flex-col items-center justify-between gap-4 px-2 sm:flex-row">
                <div className="relative flex-1 max-w-lg w-full">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-blue-500" />
                    <Input
                        placeholder="Search attached itineraries"
                        className="h-10 w-full rounded-md border-border bg-background pl-10 text-sm placeholder:text-muted-foreground focus:border-blue-500"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
                <div className="flex gap-2">
                    <Button
                        onClick={() => setUploadOpen(true)}
                        className="h-10 crm-icon-primary px-4 font-medium shadow-none hover:bg-primary/25 flex gap-2 items-center"
                    >
                        <Upload className="h-4 w-4" />
                        Upload Itinerary
                    </Button>
                    <Button
                        onClick={() => setAttachOpen(true)}
                        className="bg-emerald-500 hover:bg-emerald-600 text-white h-10 font-medium px-6 shadow-sm flex gap-2 items-center"
                    >
                        <Paperclip className="h-4 w-4" />
                        Attach
                    </Button>
                </div>
            </div>

            <div className="min-h-[150px]">
                {isLoading ? (
                    <div className="text-center text-muted-foreground py-12">Loading...</div>
                ) : filteredLinked.length === 0 ? (
                    <div className="crm-empty-state">
                        <Map className="mx-auto mb-3 h-12 w-12 text-muted-foreground" />
                        <p className="font-medium text-foreground">No itineraries attached</p>
                        <p className="mt-1 text-sm text-muted-foreground">Upload or attach travel itineraries to plan the trip details.</p>
                    </div>
                ) : (
                    <div className="grid gap-2 sm:grid-cols-2">
                        {filteredLinked.map((item) => (
                            <div
                                key={item.itinerary.id}
                                className="flex items-start justify-between gap-3 rounded-md border border-border bg-card px-3 py-2.5"
                            >
                                <div className="min-w-0">
                                    <p className="truncate text-sm font-semibold text-foreground">{item.itinerary.name}</p>
                                    <p className="truncate text-xs text-muted-foreground">
                                        {item.itinerary.destination_names?.length
                                            ? item.itinerary.destination_names.join(", ")
                                            : "No destination"}
                                    </p>
                                </div>
                                <div className="flex items-center gap-1 shrink-0">
                                    <button
                                        type="button"
                                        title="Download PDF"
                                        onClick={() => openPdf(item.itinerary.pdf_file_id)}
                                        className="text-blue-500 hover:text-blue-600 p-1"
                                    >
                                        <Download className="h-4 w-4" />
                                    </button>
                                    <button
                                        type="button"
                                        title="Remove"
                                        onClick={() => handleUnlink(item.itinerary.id)}
                                        disabled={unlinkMutation.isPending}
                                        className="text-muted-foreground hover:text-red-600 p-1"
                                    >
                                        <X className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <UploadItineraryDrawer
                open={uploadOpen}
                onOpenChange={setUploadOpen}
                opportunityId={opportunityId}
            />

            <AttachItineraryDialog
                open={attachOpen}
                onOpenChange={setAttachOpen}
                linkedIds={linkedIds}
                isLinking={linkMutation.isPending}
                onAttach={async (itineraryId) => {
                    try {
                        await linkMutation.mutateAsync(itineraryId);
                        toast.success("Itinerary attached");
                        setAttachOpen(false);
                    } catch {
                        toast.error("Failed to attach itinerary");
                    }
                }}
            />
        </div>
    );
}

interface AttachItineraryDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    linkedIds: Set<string>;
    isLinking: boolean;
    onAttach: (itineraryId: string) => void;
}

function AttachItineraryDialog({ open, onOpenChange, linkedIds, isLinking, onAttach }: AttachItineraryDialogProps) {
    const [search, setSearch] = useState("");
    const [debounced, setDebounced] = useState("");

    useEffect(() => {
        const t = setTimeout(() => setDebounced(search.trim()), 300);
        return () => clearTimeout(t);
    }, [search]);

    // Only fetch while the dialog is open.
    const { data: results, isLoading } = useItineraries(open ? debounced || undefined : undefined);
    const available = (results || []).filter((i) => !linkedIds.has(i.id));

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle>Attach an itinerary</DialogTitle>
                    <DialogDescription>Search by name or destination, then select one to attach.</DialogDescription>
                </DialogHeader>

                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        autoFocus
                        placeholder="Search itineraries..."
                        className="pl-9"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>

                <div className="max-h-72 overflow-y-auto -mx-1 px-1">
                    {isLoading ? (
                        <div className="flex items-center justify-center py-8 text-muted-foreground">
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Loading...
                        </div>
                    ) : available.length === 0 ? (
                        <p className="py-8 text-center text-sm text-muted-foreground">No itineraries found</p>
                    ) : (
                        <ul className="divide-y divide-border">
                            {available.map((itinerary) => (
                                <li key={itinerary.id}>
                                    <button
                                        type="button"
                                        disabled={isLinking}
                                        onClick={() => onAttach(itinerary.id)}
                                        className="flex w-full items-center justify-between gap-3 px-2 py-2.5 text-left hover:bg-muted/60 rounded-md disabled:opacity-50"
                                    >
                                        <span className="min-w-0">
                                            <span className="block truncate text-sm font-medium text-foreground">{itinerary.name}</span>
                                            <span className="block truncate text-xs text-muted-foreground">
                                                {itinerary.destination_names?.length ? itinerary.destination_names.join(", ") : "No destination"}
                                            </span>
                                        </span>
                                        <Paperclip className="h-4 w-4 text-emerald-500 shrink-0" />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
