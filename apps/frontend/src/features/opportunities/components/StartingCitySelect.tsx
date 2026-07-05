"use client";

import { useCallback, useState } from "react";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { locationService } from "@/lib/api/services/locations.service";

/**
 * Server-searched city picker for the opportunity Starting City field.
 * Stores the plain city name so `custom_fields.starting_city` stays a string
 * and legacy free-text values still display (they seed the option list).
 */
export function StartingCitySelect({
    value,
    onChange,
}: {
    value?: string;
    onChange: (value: string) => void;
}) {
    const [options, setOptions] = useState<{ label: string; value: string }[]>([]);
    const [loading, setLoading] = useState(false);

    const handleSearch = useCallback(async (query: string, signal?: AbortSignal) => {
        // 1-char queries match thousands of world cities; wait for 2 chars.
        if (!query || query.trim().length < 2) {
            setOptions([]);
            setLoading(false);
            return;
        }
        setLoading(true);
        try {
            const res = await locationService.searchCities(query, undefined, undefined, signal);
            // Same-named cities exist across states; the field only stores the
            // name, so de-dupe to one option per name. Cap defensively — the
            // dropdown renderer chokes on huge lists.
            const names = Array.from(new Set(res.cities.map((c) => c.name))).slice(0, 50);
            setOptions(names.map((name) => ({ label: name, value: name })));
            setLoading(false);
        } catch (err) {
            // Aborted = superseded by a newer keystroke; keep the spinner on.
            if (!signal?.aborted) {
                console.error("Starting city search error", err);
                setLoading(false);
            }
        }
    }, []);

    // Keep the selected value visible as the trigger label even when the
    // current search results don't include it.
    const merged =
        value && !options.some((o) => o.value === value)
            ? [{ label: value, value }, ...options]
            : options;

    return (
        <SearchableSelect
            options={merged}
            value={value || ""}
            onValueChange={onChange}
            onSearch={handleSearch}
            isLoading={loading}
            placeholder="Search city"
        />
    );
}
