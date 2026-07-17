"use client";

import { useGetEvents } from "@/features/events/api/use-events";
import { EventList } from "@/features/events/components/event-list";
import { Button } from "@/components/ui/button";
import { Plus, CalendarDays } from "lucide-react";
import { ModuleTitle } from "@/components/shared/module-title";
import Link from "next/link";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { PermissionGate } from "@/components/permissions/PermissionGate";

export default function EventsPage() {
    const [page, setPage] = useState(1);
    const [search, setSearch] = useState("");
    const { data, isLoading } = useGetEvents(page, 10, search);

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle
                    icon={CalendarDays}
                    title="Events"
                    description="Manage your calendar, meetings, and calls."
                />
                <PermissionGate permission="create_event">
                    <Button asChild>
                        <Link href="/events/new">
                            <Plus className="mr-2 h-4 w-4" /> Create Event
                        </Link>
                    </Button>
                </PermissionGate>
            </div>

            <div className="flex items-center space-x-2">
                <Input
                    placeholder="Search events..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="max-w-sm"
                />
            </div>

            <EventList events={data?.events || []} isLoading={isLoading} />

            {data && data.pagination.pages > 1 && (
                <div className="flex justify-center gap-2 mt-4">
                    <Button
                        variant="outline"
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page === 1}
                    >
                        Previous
                    </Button>
                    <span className="py-2">
                        Page {data.pagination.current_page} of {data.pagination.pages}
                    </span>
                    <Button
                        variant="outline"
                        onClick={() => setPage((p) => Math.min(data.pagination.pages, p + 1))}
                        disabled={page === data.pagination.pages}
                    >
                        Next
                    </Button>
                </div>
            )}
        </div>
    );
}
