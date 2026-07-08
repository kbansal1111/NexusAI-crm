"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import { territoryService, type Territory, type Region } from "@/lib/api/services/territory.service";
import { usersExtraService } from "@/lib/api/services/users-extra.service";
import { MultiSelect } from "@/components/ui/multi-select";
import { locationService, type Country as GeoCountry, type State as GeoState } from "@/lib/api/services/locations.service";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  territory?: Territory | null;
  regions: Region[];
  onSaved: () => void;
}

const EMPTY: Omit<Territory, "id" | "region_name"> = {
  name: "",
  code: "",
  description: "",
  region_id: "",
  parent_territory_id: null,
  countries: [],
  states: [],
  postal_codes: [],
  manager_id: null,
  assignment_type: "geographic",
  is_active: true,
};

function csv(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function TerritoryFormDialog({ open, onOpenChange, territory, regions, onSaved }: Props) {
  const [form, setForm] = useState<typeof EMPTY>(EMPTY);
  const [users, setUsers] = useState<Array<{ id: string; name: string; email?: string }>>([]);
  const [saving, setSaving] = useState(false);

  // Country/State are picked from the SAME canonical location source the Account
  // form uses (values stored by NAME), so a territory's countries/states match
  // an account's billing_country/billing_state exactly — no case/spelling drift.
  const [countryOpts, setCountryOpts] = useState<GeoCountry[]>([]);
  const [stateOpts, setStateOpts] = useState<GeoState[]>([]);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [loadingStates, setLoadingStates] = useState(false);
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
  const mergeStates = (list: GeoState[]) => {
    setStateOpts((prev) => {
      const map = new Map(prev.map((s) => [s.name, s]));
      for (const s of list) map.set(s.name, s);
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
  const handleStateSearch = (q: string, signal?: AbortSignal) => {
    if (!q) return;
    const sel = form.countries || [];
    const countryId = sel.length === 1 ? countryByName.current.get(sel[0])?.id : undefined;
    setLoadingStates(true);
    locationService
      .searchStates(q, countryId, signal)
      .then((r) => mergeStates(r.states))
      .catch(() => {})
      .finally(() => setLoadingStates(false));
  };

  useEffect(() => {
    if (!open) return;
    usersExtraService
      .getAllActive()
      .then((data: any) => {
        const arr = Array.isArray(data) ? data : data?.users || [];
        setUsers(
          arr.map((u: any) => ({ id: u.id || u._id, name: u.name, email: u.email }))
        );
      })
      .catch(() => {});
  }, [open]);

  useEffect(() => {
    if (territory) {
      const { id: _id, region_name: _rn, ...rest } = territory;
      setForm({ ...EMPTY, ...rest });
    } else {
      setForm(EMPTY);
    }
  }, [territory, open]);

  // Seed the country dropdown with the popular list when the dialog opens.
  useEffect(() => {
    if (!open) return;
    setLoadingCountries(true);
    locationService
      .getCountries(true)
      .then((r) => mergeCountries(r.countries))
      .catch(() => {})
      .finally(() => setLoadingCountries(false));
  }, [open]);

  // Load the states belonging to every selected country so the State dropdown
  // only offers states that actually sit inside the territory's countries.
  const selectedCountriesKey = (form.countries || []).join(",");
  useEffect(() => {
    if (!open) return;
    const names = form.countries || [];
    if (names.length === 0) return;
    let cancelled = false;
    (async () => {
      setLoadingStates(true);
      try {
        for (const name of names) {
          let c = countryByName.current.get(name);
          if (!c) {
            const res = await locationService.searchCountries(name);
            mergeCountries(res.countries);
            c = res.countries.find((x) => x.name === name) || countryByName.current.get(name);
          }
          if (c && !cancelled) {
            const st = await locationService.getStates(c.id);
            if (!cancelled) mergeStates(st.states);
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

  const submit = async () => {
    if (!form.name.trim()) return toast.error("Name is required");
    if (!form.region_id) return toast.error("Region is required");
    setSaving(true);
    try {
      if (territory) {
        await territoryService.updateTerritory(territory.id, form);
        toast.success("Territory updated");
      } else {
        await territoryService.createTerritory(form);
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
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{territory ? "Edit Territory" : "Create Territory"}</DialogTitle>
          <DialogDescription>
            Territories are geo-matched to leads via postal code → state → country in that priority.
            Wildcards like &ldquo;56*&rdquo; match any postal code starting with 56.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="tname">Name *</Label>
              <Input
                id="tname"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="tcode">Code</Label>
              <Input
                id="tcode"
                value={form.code || ""}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>Region *</Label>
              <Select
                value={form.region_id}
                onValueChange={(v) => setForm({ ...form, region_id: v })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select region" />
                </SelectTrigger>
                <SelectContent>
                  {regions.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>Assignment Type</Label>
              <Select
                value={form.assignment_type || "geographic"}
                onValueChange={(v) =>
                  setForm({ ...form, assignment_type: v as Territory["assignment_type"] })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="geographic">Geographic</SelectItem>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="rule_based">Rule-based</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label>Countries</Label>
            <MultiSelect
              options={countryOpts.map((c) => ({ label: c.name, value: c.name }))}
              selected={form.countries || []}
              onChange={(vals) => setForm({ ...form, countries: vals })}
              onSearch={handleCountrySearch}
              isLoading={loadingCountries}
              placeholder="Search and select countries"
            />
            <p className="text-xs text-muted-foreground">
              Picked from the shared location list so values match an account&apos;s billing country exactly.
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label>States</Label>
            <MultiSelect
              options={stateOpts.map((s) => ({ label: s.name, value: s.name }))}
              selected={form.states || []}
              onChange={(vals) => setForm({ ...form, states: vals })}
              onSearch={handleStateSearch}
              isLoading={loadingStates}
              placeholder={(form.countries || []).length ? "Search and select states" : "Select a country first"}
              disabled={(form.countries || []).length === 0}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="tpc">Postal codes (comma-separated; use * for wildcards)</Label>
            <Input
              id="tpc"
              placeholder="560001, 56*, 700*"
              value={(form.postal_codes || []).join(", ")}
              onChange={(e) => setForm({ ...form, postal_codes: csv(e.target.value) })}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>Territory Manager (BD User)</Label>
              <Select
                value={form.manager_id || "__none__"}
                onValueChange={(v) =>
                  setForm({ ...form, manager_id: v === "__none__" ? null : v })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">None</SelectItem>
                  {users.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                The one person who owns this territory — sees every opportunity in it
                (country/state/region).
              </p>
            </div>
            <div className="flex items-center gap-2 pt-7">
              <Switch
                id="tactive"
                checked={form.is_active ?? true}
                onCheckedChange={(v) => setForm({ ...form, is_active: v })}
              />
              <Label htmlFor="tactive" className="cursor-pointer">Active</Label>
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="tdesc">Description</Label>
            <Textarea
              id="tdesc"
              rows={2}
              value={form.description || ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
            {territory ? "Save Changes" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
