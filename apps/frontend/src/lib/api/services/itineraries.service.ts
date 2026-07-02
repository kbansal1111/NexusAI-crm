import { apiClient } from "@/lib/api/client";
import { Itinerary, ItineraryFilters, ItineraryListResponse, UploadItineraryInput } from "@/features/itineraries/types";

const BASE_URL = "/itineraries";

export const itinerariesService = {
    getItineraries: async (params?: ItineraryFilters): Promise<ItineraryListResponse> => {
        const response = await apiClient.get<ItineraryListResponse>(`${BASE_URL}/`, { params });
        return response.data;
    },

    getItinerary: async (id: string): Promise<Itinerary> => {
        const response = await apiClient.get<Itinerary>(`${BASE_URL}/${id}`);
        return response.data;
    },

    uploadItinerary: async ({ name, destinationIds, file, opportunityId }: UploadItineraryInput): Promise<Itinerary> => {
        const formData = new FormData();
        formData.append("name", name);
        formData.append("destination_ids", destinationIds);
        formData.append("file", file);
        if (opportunityId) formData.append("opportunity_id", opportunityId);

        const response = await apiClient.post<Itinerary>(`${BASE_URL}/upload`, formData, {
            headers: { "Content-Type": "multipart/form-data" },
        });
        return response.data;
    },

    updateItinerary: async (id: string, data: Partial<Pick<Itinerary, "name" | "notes" | "is_active">>): Promise<Itinerary> => {
        const response = await apiClient.put<Itinerary>(`${BASE_URL}/${id}`, data);
        return response.data;
    },

    deleteItinerary: async (id: string): Promise<void> => {
        await apiClient.delete(`${BASE_URL}/${id}`);
    },

    linkToOpportunity: async (opportunityId: string, itineraryId: string): Promise<void> => {
        await apiClient.post(`${BASE_URL}/opportunity/${opportunityId}/link?itinerary_id=${itineraryId}`);
    },

    unlinkFromOpportunity: async (opportunityId: string, itineraryId: string): Promise<void> => {
        await apiClient.delete(`${BASE_URL}/opportunity/${opportunityId}/unlink?itinerary_id=${itineraryId}`);
    },

    // Fetch the itinerary PDF as an authenticated blob and return an object URL.
    // Streams through the backend so it works for both S3 and local storage, and
    // is gated by view_itinerary (not view_file).
    getPdfObjectUrl: async (itineraryId: string): Promise<string> => {
        const response = await apiClient.get(`${BASE_URL}/${itineraryId}/pdf`, { responseType: "blob" });
        return URL.createObjectURL(response.data as Blob);
    },
};
