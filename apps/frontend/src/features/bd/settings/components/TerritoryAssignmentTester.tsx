"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, MapPin, AlertCircle, CheckCircle2 } from "lucide-react";
import { SearchableSelect } from "@/components/ui/searchable-select";
import {
  territoryService,
  type TerritoryAssignmentResult,
} from "@/lib/api/services/territory.service";
import {
  locationService,
  type Country as GeoCountry,
  type State as GeoState,
} from "@/lib/api/services/locations.service";

/**
 * Sandbox for admins: pick an address, see which territory the system would
 * auto-assign. Country/State are the same canonical dropdowns (stored by NAME)
 * as the Account/Territory forms, so the test matches production exactly —
 * no free-text codes like "IN"/"KA" that never match stored names.
 */
export function TerritoryAssignmentTester() {
  const [country, setCountry] = useState("");
  const [state, setState] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TerritoryAssignmentResult | null>(null);
  const [noMatch, setNoMatch] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [countryOpts, setCountryOpts] = useState<GeoCountry[]>([]);
  const [stateOpts, setStateOpts] = useState<GeoState[]>([]);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [loadingStates, setLoadingStates] = useState(false);
  const countryByName = useRef<Map<string, GeoCountry>>(new Map());

  const mergeCountries = (list: GeoCountry[]) => {
    for (const c of list) countryByName.current.set(c.name, c);
    setCountryOpts((prev) => {
      const map = new Map(prev.map((c) => [c.name, c]));
      for (const c of list) map.set(c.name, c);
      return Array.from(map.values());
    });
  };

  useEffect(() => {
    setLoadingCountries(true);
    locationService
      .getCountries(true)
      .then((r) => mergeCountries(r.countries))
      .catch(() => {})
      .finally(() => setLoadingCountries(false));
  }, []);

  const handleCountrySearch = (q: string, signal?: AbortSignal) => {
    if (!q) return;
    setLoadingCountries(true);
    locationService
      .searchCountries(q, signal)
      .then((r) => mergeCountries(r.countries))
      .catch(() => {})
      .finally(() => setLoadingCountries(false));
  };

  // Proper cascade: picking a country loads exactly that country's states.
  const onCountryChange = (name: string) => {
    setCountry(name);
    setState("");
    setStateOpts([]);
    const c = countryByName.current.get(name);
    if (!c) return;
    setLoadingStates(true);
    locationService
      .getStates(c.id)
      .then((r) => setStateOpts(r.states))
      .catch(() => {})
      .finally(() => setLoadingStates(false));
  };

  const run = async () => {
    if (!country && !state && !postalCode) {
      setError("Provide at least one of: country, state, postal code");
      return;
    }
    setLoading(true);
    setResult(null);
    setNoMatch(false);
    setError(null);
    try {
      const res = await territoryService.checkAssignment({
        country: country || undefined,
        state: state || undefined,
        postal_code: postalCode || undefined,
      });
      if (!res) {
        setNoMatch(true);
      } else {
        setResult(res);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Lookup failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPin className="h-4 w-4" />
          Assignment Tester
        </CardTitle>
        <CardDescription>
          Simulate how an inbound lead address resolves to a territory. Tests the same
          priority chain used in production: postal exact → postal wildcard → state → country.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="grid gap-1.5">
            <Label>Country</Label>
            <SearchableSelect
              options={countryOpts.map((c) => ({ label: c.name, value: c.name }))}
              value={country}
              onValueChange={onCountryChange}
              onSearch={handleCountrySearch}
              isLoading={loadingCountries}
              placeholder="Select country"
              searchPlaceholder="Search country"
            />
          </div>
          <div className="grid gap-1.5">
            <Label>State</Label>
            <SearchableSelect
              options={stateOpts.map((s) => ({ label: s.name, value: s.name }))}
              value={state}
              onValueChange={setState}
              isLoading={loadingStates}
              placeholder={country ? "Select state" : "Select a country first"}
              searchPlaceholder="Search state"
              disabled={!country}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="t_pc">Postal Code</Label>
            <Input id="t_pc" value={postalCode} onChange={(e) => setPostalCode(e.target.value)} placeholder="560001" />
          </div>
        </div>
        <Button onClick={run} disabled={loading}>
          {loading && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
          Test
        </Button>

        {error && (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}
        {noMatch && (
          <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            No territory matches this address. The lead would be created without a BD owner.
          </div>
        )}
        {result && (
          <div className="rounded-md border p-3 space-y-2 bg-muted/30">
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span className="font-medium">Match found</span>
              <Badge variant="outline">via {result.matched_by}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">Territory</p>
                <p className="font-medium">{result.territory_name}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Region</p>
                <p className="font-medium">{result.region_name || "—"}</p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
