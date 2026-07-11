"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { territoryService, type Territory } from "@/lib/api/services/territory.service";
import { destinationsService, type Destination } from "@/lib/api/services/destinations.service";
import { MultiSelect } from "@/components/ui/multi-select";
import { locationService, type Country as GeoCountry, type State as GeoState } from "@/lib/api/services/locations.service";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  territory?: Territory | null;
  onSaved: () => void;
}

// Simplified single-form territory (mirrors the client's legacy CRM):
// Name + Countries + States + Destinations. The BD user who owns a territory
// is assigned on the Admin → Users form (single assignment path).
// Legacy fields (code, region, postal codes, manager, description) are
// preserved on existing records by only sending the fields this form manages.
interface FormState {
  name: string;
  countries: string[];
  states: string[];
  destinations: string[];
}

const EMPTY: FormState = {
  name: "",
  countries: [],
  states: [],
  destinations: [],
};

export function TerritoryFormDialog({ open, onOpenChange, territory, onSaved }: Props) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);

  // Country/State are picked from the SAME canonical location source the Account
  // form uses (values stored by NAME), so a territory's countries/states match
  // an account's billing_country/billing_state exactly — no case/spelling drift.
  const [countryOpts, setCountryOpts] = useState<GeoCountry[]>([]);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [loadingStates, setLoadingStates] = useState(false);
  // States are grouped per selected country so the State dropdown never offers
  // a state outside the territory's countries (proper country → state cascade,
  // same rule as the Lead/Account address forms).
  const [statesByCountry, setStatesByCountry] = useState<Record<string, GeoState[]>>({});
  const [allDestinations, setAllDestinations] = useState<Destination[]>([]);
  // name -> Country, accumulated across popular + searches, to resolve the id
  // needed to load a country's states.
  const countryByName = useRef<Map<string, GeoCountry>>(new Map());

  const mergeCountries = (list: GeoCountry[]) => {
    for (const c of list) countryByName.current.set(c.name, c);
    setCountryOpts((prev) => {
      const map = new Map(prev.map((c) => [c.name, c]));
      for (const c of list) map.set(c.name, c);
      return Array.from(map.values());
    });
  };

  const handleCountrySearch = (q: string, signal?: AbortSignal) => {
    if (!q) return;
    setLoadingCountries(true);
    locationService
      .searchCountries(q, signal)
      .then((r) => mergeCountries(r.countries))
      .catch(() => {})
      .finally(() => setLoadingCountries(false));
  };

  useEffect(() => {
    if (territory) {
      setForm({
        name: territory.name || "",
        countries: territory.countries || [],
        states: territory.states || [],
        destinations: territory.destinations || [],
      });
    } else {
      setForm(EMPTY);
    }
  }, [territory, open]);

  // Seed the country dropdown (popular list) + destination picklist on open.
  useEffect(() => {
    if (!open) return;
    setLoadingCountries(true);
    locationService
      .getCountries(true)
      .then((r) => mergeCountries(r.countries))
      .catch(() => {})
      .finally(() => setLoadingCountries(false));
    destinationsService
      .getDestinations()
      .then((r) => setAllDestinations(r.destinations))
      .catch(() => {});
  }, [open]);

  // Load each selected country's states; drop entries for deselected countries
  // so the State options always reflect exactly the selected countries.
  const selectedCountriesKey = (form.countries || []).join(",");
  useEffect(() => {
    if (!open) return;
    const names = form.countries || [];
    setStatesByCountry((prev) => {
      const kept: Record<string, GeoState[]> = {};
      for (const n of names) if (prev[n]) kept[n] = prev[n];
      return kept;
    });
    const missing = names.filter((n) => !(n in statesByCountry));
    if (missing.length === 0) return;
    let cancelled = false;
    (async () => {
      setLoadingStates(true);
      try {
        for (const name of missing) {
          let c = countryByName.current.get(name);
          if (!c) {
            const res = await locationService.searchCountries(name);
            mergeCountries(res.countries);
            c = res.countries.find((x) => x.name === name) || countryByName.current.get(name);
          }
          if (c && !cancelled) {
            const st = await locationService.getStates(c.id);
            if (!cancelled) {
              setStatesByCountry((prev) => ({ ...prev, [name]: st.states }));
            }
          }
        }
      } catch {
        /* best-effort; existing values still display as-is */
      } finally {
        if (!cancelled) setLoadingStates(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selectedCountriesKey]);

  // State options = union of the selected countries' states, deduped by name.
  const stateOpts = useMemo(() => {
    const map = new Map<string, GeoState>();
    for (const country of form.countries) {
      for (const s of statesByCountry[country] || []) map.set(s.name, s);
    }
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [form.countries, statesByCountry]);

  // Destination options: only destinations mapped to a selected country (ones
  // with no country mapping stay available), deduped by name so repeated
  // seed rows (e.g. two "Wellington"s) don't produce duplicate React keys.
  const destOpts = useMemo(() => {
    const selected = new Set(form.countries);
    const map = new Map<string, string>(); // name -> label
    for (const d of allDestinations) {
      if (selected.size > 0 && d.country_name && !selected.has(d.country_name)) continue;
      if (!map.has(d.name)) {
        map.set(d.name, d.country_name && selected.size === 0 ? `${d.name} (${d.country_name})` : d.name);
      }
    }
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [allDestinations, form.countries]);

  // Country change prunes selected states/destinations that belonged to a
  // removed country (values we can't map — legacy data — are left alone).
  const onCountriesChange = (vals: string[]) => {
    setForm((prev) => {
      const keep = new Set<string>();
      for (const country of vals) {
        for (const s of statesByCountry[country] || []) keep.add(s.name);
      }
      const known = new Set<string>();
      for (const list of Object.values(statesByCountry)) {
        for (const s of list) known.add(s.name);
      }
      const destByName = new Map(allDestinations.map((d) => [d.name, d.country_name]));
      const countrySet = new Set(vals);
      return {
        ...prev,
        countries: vals,
        states: prev.states.filter((s) => keep.has(s) || !known.has(s)),
        destinations:
          vals.length === 0
            ? prev.destinations
            : prev.destinations.filter((name) => {
                const c = destByName.get(name);
                return !c || countrySet.has(c);
              }),
      };
    });
  };

  const submit = async () => {
    if (!form.name.trim()) return toast.error("Name is required");
    if (form.countries.length === 0) return toast.error("Select at least one country");
    setSaving(true);
    try {
      if (territory) {
        // Send only what this form manages so legacy fields on old records
        // (manager, code, region, postal codes, …) are left untouched.
        await territoryService.updateTerritory(territory.id, form);
        toast.success("Territory updated");
      } else {
        await territoryService.createTerritory({
          ...form,
          assignment_type: "geographic",
          is_active: true,
        });
        toast.success("Territory created");
      }
      onSaved();
      onOpenChange(false);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{territory ? "Edit Territory" : "Add Territory"}</DialogTitle>
          <DialogDescription>
            New opportunities are matched to a territory by the customer&apos;s state, then
            country. Assign this territory to its BD user on the Admin → Users form.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="tname">Name *</Label>
            <Input
              id="tname"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Usually the BD user's name"
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Country *</Label>
            <MultiSelect
              options={countryOpts.map((c) => ({ label: c.name, value: c.name }))}
              selected={form.countries}
              onChange={onCountriesChange}
              onSearch={handleCountrySearch}
              isLoading={loadingCountries}
              placeholder="Select countries"
            />
          </div>

          <div className="grid gap-1.5">
            <Label>State(s)</Label>
            <MultiSelect
              options={stateOpts.map((s) => ({ label: s.name, value: s.name }))}
              selected={form.states}
              onChange={(vals) => setForm({ ...form, states: vals })}
              isLoading={loadingStates}
              placeholder={form.countries.length ? "Search state" : "Select a country first"}
              disabled={form.countries.length === 0}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Destination(s)</Label>
            <MultiSelect
              options={destOpts}
              selected={form.destinations}
              onChange={(vals) => setForm({ ...form, destinations: vals })}
              placeholder="Select destinations"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
            {territory ? "Save" : "Add"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
