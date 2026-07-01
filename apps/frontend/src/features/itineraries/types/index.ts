// An itinerary is now a named PDF organized by destination (see backend
// Itinerary model). The heavy day-by-day builder has been removed.
export interface Itinerary {
    id: string;
    name: string;
    description?: string;

    destination_ids: string[];
    destination_names: string[];
    tour_starts_from?: string;
    total_days?: number | null;
    total_nights?: number | null;

    // Points at the uploaded PDF File record; download via /files/{id}/url.
    pdf_file_id?: string | null;

    is_template: boolean;
    notes?: string;
    tenant_id: string;
    owner_id: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

// Paginated list response from GET /itineraries/.
export interface ItineraryListResponse {
    itineraries: Itinerary[];
    total: number;
}

// Query params for the list endpoint (sent as axios params).
export interface ItineraryFilters {
    search?: string;
    is_template?: boolean;
    [key: string]: unknown;
}

// Payload for the multipart upload (POST /itineraries/upload).
export interface UploadItineraryInput {
    name: string;
    destinationIds: string; // comma-separated picklist destination ids
    file: File;
    opportunityId?: string;
}
