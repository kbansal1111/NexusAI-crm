import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Itinerary, UploadItineraryInput } from "../types";
import { apiClient } from "@/lib/api/client";
import { itinerariesService } from "@/lib/api/services/itineraries.service";

export const itinerariesKeys = {
    all: ['itineraries'] as const,
    lists: () => [...itinerariesKeys.all, 'list'] as const,
    list: (search: string) => [...itinerariesKeys.lists(), { search }] as const,
    details: () => [...itinerariesKeys.all, 'detail'] as const,
    detail: (id: string) => [...itinerariesKeys.details(), id] as const,
    opportunity: (id: string) => [...itinerariesKeys.all, 'opportunity', id] as const,
};

// List itineraries, optionally filtered by a server-side search (name + destination).
export const useItineraries = (search?: string) => {
    return useQuery({
        queryKey: itinerariesKeys.list(search ?? ""),
        queryFn: async () => {
            const { data } = await apiClient.get('/itineraries/', {
                params: search ? { search } : undefined,
            });
            return data.itineraries as Itinerary[];
        },
    });
};

export const useItinerary = (id: string) => {
    return useQuery({
        queryKey: itinerariesKeys.detail(id),
        queryFn: async () => {
            const { data } = await apiClient.get(`/itineraries/${id}`);
            return data as Itinerary;
        },
        enabled: !!id,
    });
};

export const useOpportunityItineraries = (opportunityId: string) => {
    return useQuery({
        queryKey: itinerariesKeys.opportunity(opportunityId),
        queryFn: async () => {
            const { data } = await apiClient.get(`/itineraries/opportunity/${opportunityId}`);
            return data.itineraries as { itinerary: Itinerary; notes?: string }[];
        },
        enabled: !!opportunityId,
    });
};

// Upload a PDF itinerary; optionally auto-attach it to an opportunity.
export const useUploadItinerary = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (input: UploadItineraryInput) => itinerariesService.uploadItinerary(input),
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: itinerariesKeys.lists() });
            if (variables.opportunityId) {
                queryClient.invalidateQueries({ queryKey: itinerariesKeys.opportunity(variables.opportunityId) });
            }
        },
    });
};

export const useUpdateItinerary = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, payload }: { id: string; payload: Partial<Pick<Itinerary, "name" | "notes" | "is_active">> }) => {
            return itinerariesService.updateItinerary(id, payload);
        },
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: itinerariesKeys.detail(variables.id) });
            queryClient.invalidateQueries({ queryKey: itinerariesKeys.lists() });
        },
    });
};

export const useDeleteItinerary = () => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => itinerariesService.deleteItinerary(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: itinerariesKeys.lists() });
        },
    });
};

// Attach an existing itinerary to an opportunity.
export const useLinkItinerary = (opportunityId: string) => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (itineraryId: string) => itinerariesService.linkToOpportunity(opportunityId, itineraryId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: itinerariesKeys.opportunity(opportunityId) });
        },
    });
};

// Detach an itinerary from an opportunity (does not delete the itinerary).
export const useUnlinkItinerary = (opportunityId: string) => {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (itineraryId: string) => itinerariesService.unlinkFromOpportunity(opportunityId, itineraryId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: itinerariesKeys.opportunity(opportunityId) });
        },
    });
};
