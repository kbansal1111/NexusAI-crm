"use client";

import * as React from "react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Plus, X } from "lucide-react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  entityViewsService,
  type EntityView,
  type FilterRule,
} from "@/lib/api/services/entity-views.service";
import {
  customFieldsService,
  type EntityType,
} from "@/lib/api/services/field-registry.service";
import { accountService } from "@/features/accounts/services/accountService";
import { contactsService } from "@/lib/api/services/contacts.service";
import { destinationsService } from "@/lib/api/services/destinations.service";
import { locationService } from "@/lib/api/services/locations.service";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { formatDate } from "@/lib/format";
import {
  operatorsForType,
  operatorArityForType,
  isRelativeToken,
  RELATIVE_TOKEN_LABEL,
  STANDARD_DATE_CHIPS,
  TRAVEL_DATE_CHIPS,
} from "./fieldMeta";
import type { LogicalType } from "./fieldMeta";
import {
  standardFieldsFor,
  realCustomFields,
  accountRefFieldsFor,
  contactRefFieldsFor,
  additionalFieldKeysFor,
  type OptionList,
} from "./accountFields";
import { AsyncEntitySelect } from "./AsyncEntitySelect";
import { DateFilterValue } from "./DateFilterValue";

// Geographic string fields rendered as a type-to-search location picker (the
// stored value is the location NAME, matching how these columns persist and how
// the backend string clause matches them).
type GeoKind = "country" | "state" | "city";
const GEO_KIND: Record<string, GeoKind> = {
  billing_country: "country",
  country: "country",
  billing_state: "state",
  state: "state",
  billing_city: "city",
  city: "city",
  "custom_fields.starting_city": "city",
  // Contact mailing address.
  mailing_country: "country",
  mailing_state: "state",
  mailing_city: "city",
  // Supplier service-area arrays (stored as location-name arrays).
  countries: "country",
  states: "state",
  service_cities: "city",
};
const GEO_PLACEHOLDER: Record<GeoKind, string> = {
  country: "Search countries…",
  state: "Search states…",
  city: "Search cities…",
};

// City/state names repeat across regions; collapse to distinct names (the value
// is just the name string) so the option list has no duplicate keys.
function uniqueNamed(items: { name: string }[]): { id: string; name: string }[] {
  const seen = new Set<string>();
  const out: { id: string; name: string }[] = [];
  for (const it of items) {
    const name = (it.name || "").trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push({ id: name, name });
  }
  return out;
}

type Row = { field: string; operator: string; value: any };
type FieldMeta = { key: string; label: string; type: LogicalType };

const ADD = "additional:";

// "Show me" header label, per module (mirrors each list's record noun rather
// than always reading "All accounts").
const SHOW_ME_LABEL: Record<EntityType, string> = {
  account: "All accounts",
  personal_account: "All person accounts",
  contact: "All contacts",
  lead: "All leads",
  opportunity: "All opportunities",
  supplier: "All suppliers",
  task: "All tasks",
};

/**
 * Destination filter value editor — multi-select chip picker mirroring the
 * Lead/Opportunity forms. Stores an array of destination ids; an "is" filter
 * matches any selected destination. Options are the preloaded full set, so
 * search/filter is local (never a giant unscrolled list).
 */
function DestinationMultiSelect({
  value,
  options,
  labelFor,
  onChange,
}: {
  value: string[];
  options: { id: string; name: string }[];
  labelFor: (id: string) => string;
  onChange: (ids: string[]) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    const base = q ? options.filter((o) => o.name.toLowerCase().includes(q)) : options;
    return base.slice(0, 50);
  }, [search, options]);
  const toggle = (id: string) =>
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  const remove = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(value.filter((v) => v !== id));
  };
  return (
    <Popover open={open} onOpenChange={setOpen} modal>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" type="button" className="h-auto min-h-9 w-full justify-between font-normal">
          <div className="flex flex-1 flex-wrap gap-1 text-left">
            {value.length > 0 ? (
              value.map((id) => (
                <Badge key={id} variant="secondary" className="rounded-sm px-1.5 text-xs font-normal">
                  {labelFor(id)}
                  <span className="ml-1 cursor-pointer" onClick={(e) => remove(id, e)} aria-label="Remove">
                    <X className="h-3 w-3" />
                  </span>
                </Badge>
              ))
            ) : (
              <span className="text-sm text-muted-foreground">Search destinations…</span>
            )}
          </div>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[--radix-popover-trigger-width] p-0"
        align="start"
        onPointerDownOutside={(e) => e.stopPropagation()}
      >
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search destinations…" value={search} onValueChange={setSearch} className="h-9" />
          <CommandList>
            <CommandEmpty>No destinations found.</CommandEmpty>
            <CommandGroup>
              {filtered.map((o) => {
                const selected = value.includes(o.id);
                return (
                  <CommandItem key={o.id} value={o.id} onSelect={() => toggle(o.id)} className="cursor-pointer">
                    <Check className={cn("mr-2 h-4 w-4", selected ? "opacity-100" : "opacity-0")} />
                    {o.name}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export function EditListFiltersDialog({
  open,
  onOpenChange,
  entity,
  view,
  onSaved,
  lookupOptions = {},
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  entity: EntityType;
  view: EntityView;
  onSaved: (view: EntityView) => void;
  /** field_key → value options for lookup filters (provided by the module table). */
  lookupOptions?: Record<string, OptionList>;
}) {
  const [scope, setScope] = React.useState<string>("all");
  const [rows, setRows] = React.useState<Row[]>([]);
  // Inline editor: editing===null closed; -1 = new row; >=0 = edit that row.
  const [editing, setEditing] = React.useState<number | null>(null);
  const [draft, setDraft] = React.useState<Row | null>(null);
  const [saving, setSaving] = React.useState(false);
  // id→name for account-reference values (resolved via search; can't live in
  // the bounded form-data list at scale).
  const [labelCache, setLabelCache] = React.useState<Record<string, string>>({});

  const standard = React.useMemo<FieldMeta[]>(() => standardFieldsFor(entity), [entity]);

  const { data: customFields = [] } = useQuery({
    queryKey: ["custom-fields", entity],
    queryFn: () => customFieldsService.list(entity, true),
    staleTime: 5 * 60 * 1000,
    enabled: open,
  });
  const custom = React.useMemo<FieldMeta[]>(
    () =>
      realCustomFields(entity, customFields).map((f) => ({
        key: ADD + f.id,
        label: f.label || f.name,
        type: "string" as LogicalType,
      })),
    [customFields, entity],
  );

  // Mirror the form / "Select Fields to display" picker: catalog fields the form
  // groups under "Additional Information" are shown under an "Additional Fields"
  // heading (alongside genuine custom fields), not under "Standard Fields".
  const additionalKeys = React.useMemo(() => additionalFieldKeysFor(entity), [entity]);
  const coreStandard = React.useMemo(
    () => standard.filter((f) => !additionalKeys.has(f.key)),
    [standard, additionalKeys],
  );
  const additional = React.useMemo<FieldMeta[]>(
    () => [...standard.filter((f) => additionalKeys.has(f.key)), ...custom],
    [standard, additionalKeys, custom],
  );
  // Async reference fields (server search) per module.
  const accountRefs = React.useMemo(() => accountRefFieldsFor(entity), [entity]);
  const contactRefs = React.useMemo(() => contactRefFieldsFor(entity), [entity]);
  const isRef = React.useCallback(
    (field: string) => accountRefs.has(field) || contactRefs.has(field),
    [accountRefs, contactRefs],
  );
  const accountSearch = React.useCallback((q: string) => accountService.autocompleteAccounts(q), []);
  const contactSearch = React.useCallback(
    (q: string, signal?: AbortSignal) =>
      contactsService.searchContactAutocomplete(q, signal).then((rs) => rs.map((r) => ({ id: r.id, name: r.name }))),
    [],
  );
  // Country / State / City search → option ids ARE the names (we store the name).
  const geoSearch = React.useMemo(
    () => ({
      country: (q: string, signal?: AbortSignal) =>
        locationService.searchCountries(q, signal).then((r) => uniqueNamed(r.countries)),
      state: (q: string, signal?: AbortSignal) =>
        locationService.searchStates(q, undefined, signal).then((r) => uniqueNamed(r.states)),
      city: (q: string, signal?: AbortSignal) =>
        locationService.searchCities(q, undefined, undefined, signal).then((r) => uniqueNamed(r.cities)),
    }),
    [],
  );

  // Destination is an unbounded picklist (cities). Rather than dump thousands of
  // options into a plain <Select>, load the full set once (for label resolution)
  // and drive the value editor with a type-to-search picker, mirroring how
  // Account/Contact references already work in this dialog.
  // Destination filter fields. Lead/Opportunity store destination IDS
  // (industry_data.destination_ids); Supplier stores destination NAMES
  // (destinations). Both drive the same multi-select picker — only the stored
  // value (id vs name) differs.
  const DEST_ID_FIELD = "industry_data.destination_ids";
  const DEST_NAME_FIELD = "destinations";
  const isDestField = React.useCallback(
    (f: string) => f === DEST_ID_FIELD || f === DEST_NAME_FIELD,
    [],
  );
  const hasDestination = React.useMemo(
    () => standard.some((f) => isDestField(f.key)),
    [standard, isDestField],
  );
  const { data: allDestinations = [], isLoading: destinationsLoading } = useQuery({
    queryKey: ["destinations", "filter-all"],
    queryFn: () => destinationsService.getDestinations({ limit: 100000 }).then((r) => r.destinations),
    staleTime: 5 * 60 * 1000,
    enabled: open && hasDestination,
  });
  const destMap = React.useMemo(() => {
    const m = new Map<string, string>();
    allDestinations.forEach((d) => m.set(d.id, d.name));
    return m;
  }, [allDestinations]);
  const fieldByKey = React.useMemo(() => {
    const m = new Map<string, FieldMeta>();
    [...standard, ...custom].forEach((f) => m.set(f.key, f));
    return m;
  }, [standard, custom]);

  React.useEffect(() => {
    if (!open) return;
    setScope(view.scope || "all");
    setRows((view.filter_rules || []).map((r) => ({ field: r.field, operator: r.operator, value: r.value ?? "" })));
    setEditing(null);
    setDraft(null);
  }, [open, view]);

  // Resolve names for any reference ids in saved rules (so summaries show names).
  React.useEffect(() => {
    if (!open) return;
    (view.filter_rules || []).forEach((r) => {
      if (!r.value || labelCache[r.value]) return;
      if (accountRefs.has(r.field)) {
        accountService.getAccount(r.value).then((a) => setLabelCache((c) => ({ ...c, [r.value]: a.name }))).catch(() => {});
      } else if (contactRefs.has(r.field)) {
        contactsService
          .getContact(r.value)
          .then((c2: any) => {
            const nm = c2.full_name || `${c2.first_name || ""} ${c2.last_name || ""}`.trim() || r.value;
            setLabelCache((c) => ({ ...c, [r.value]: nm }));
          })
          .catch(() => {});
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, view]);

  // ── helpers ───────────────────────────────────────────────────────────────
  const optionsFor = (field: string): OptionList => lookupOptions[field] || [];
  const lookupName = (field: string, value: any): string => {
    // While async labels are still resolving (destinations / account-contact
    // refs load after open), show a neutral placeholder rather than flashing the
    // raw id for a frame.
    if (isDestField(field)) {
      const vals = Array.isArray(value) ? value : value ? [value] : [];
      // Supplier destinations persist the NAME, so the value is already the label.
      if (field === DEST_NAME_FIELD) return vals.join(", ");
      return vals
        .map((id) => destMap.get(id) || labelCache[id] || (destinationsLoading ? "…" : id))
        .join(", ");
    }
    if (isRef(field)) return labelCache[value] || (value ? "…" : value);
    return optionsFor(field).find((o) => o.id === value)?.name || value;
  };

  const opLabel = (type: LogicalType, op: string) =>
    operatorsForType(type).find((o) => o.value === op)?.label || op;

  const summaryFor = (row: Row): string => {
    const fm = fieldByKey.get(row.field);
    const type = fm?.type ?? "string";
    const arity = operatorArityForType(type, row.operator);
    const label = opLabel(type, row.operator);
    if (arity === "none") return label;
    if (arity === "two") {
      const v = Array.isArray(row.value) ? row.value : ["", ""];
      if (type === "date") return `${label} ${formatDate(v[0])} to ${formatDate(v[1])}`;
      return `${label} ${v[0]} to ${v[1]}`;
    }
    if (type === "date") {
      // Relative tokens read as their literal (YESTERDAY); concrete dates format.
      const v = isRelativeToken(row.value) ? row.value : row.value ? formatDate(row.value) : "";
      return `${label} ${v}`.trim();
    }
    if (type === "bool") return `${label} ${row.value === true || row.value === "true" ? "Yes" : "No"}`;
    const v = type === "lookup" ? lookupName(row.field, row.value) : row.value;
    return `${label} ${v ?? ""}`.trim();
  };

  // ── editor actions ──────────────────────────────────────────────────────────
  const openNew = () => {
    const first = standard[0];
    setDraft({ field: first.key, operator: operatorsForType(first.type)[0].value, value: "" });
    setEditing(-1);
  };
  const openEdit = (i: number) => {
    setDraft({ ...rows[i] });
    setEditing(i);
  };
  const patchDraft = (p: Partial<Row>) => setDraft((d) => (d ? { ...d, ...p } : d));
  const onDraftField = (field: string) => {
    const type = fieldByKey.get(field)?.type ?? "string";
    setDraft({ field, operator: operatorsForType(type)[0].value, value: "" });
  };
  const commitDraft = () => {
    if (!draft) return;
    setRows((r) => {
      if (editing === -1) return [...r, draft];
      return r.map((row, i) => (i === editing ? draft : row));
    });
    setEditing(null);
    setDraft(null);
  };
  const removeRow = (i: number) => {
    setRows((r) => r.filter((_, idx) => idx !== i));
    if (editing === i) {
      setEditing(null);
      setDraft(null);
    }
  };
  const removeAll = () => {
    setRows([]);
    setEditing(null);
    setDraft(null);
  };

  const draftValueEditor = () => {
    if (!draft) return null;
    const type = fieldByKey.get(draft.field)?.type ?? "string";
    const arity = operatorArityForType(type, draft.operator);
    if (arity === "none") return <div className="text-xs text-muted-foreground">No value needed</div>;

    // Reference lookups (Account / Contact) → server search, unbounded option set.
    if (isRef(draft.field)) {
      const isAccount = accountRefs.has(draft.field);
      return (
        <AsyncEntitySelect
          value={draft.value || ""}
          label={draft.value ? labelCache[draft.value] : undefined}
          search={isAccount ? accountSearch : contactSearch}
          placeholder={isAccount ? "Search accounts…" : "Search contacts…"}
          onSelect={(id, name) => {
            patchDraft({ value: id });
            setLabelCache((c) => ({ ...c, [id]: name }));
          }}
        />
      );
    }

    // Destination → unbounded picklist; multi-select (matches ANY selected),
    // mirroring the Lead/Opportunity forms' destination chip picker.
    if (isDestField(draft.field)) {
      const selected: string[] = Array.isArray(draft.value)
        ? draft.value
        : draft.value
          ? [String(draft.value)]
          : [];
      // Supplier stores destination NAMES; option ids are the names themselves
      // (de-duped) and labels are the names. Lead/Opportunity store ids.
      const byName = draft.field === DEST_NAME_FIELD;
      const options = byName ? uniqueNamed(allDestinations) : allDestinations;
      return (
        <DestinationMultiSelect
          value={selected}
          options={options}
          labelFor={byName ? (n) => n : (id) => destMap.get(id) || labelCache[id] || id}
          onChange={(vals) => patchDraft({ value: vals })}
        />
      );
    }

    // Boolean → Yes / No (backend coerces "true"/"false"), never a text box.
    if (type === "bool") {
      return (
        <Select value={draft.value ? String(draft.value) : undefined} onValueChange={(v) => patchDraft({ value: v })}>
          <SelectTrigger className="h-9"><SelectValue placeholder="Select…" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="true">Yes</SelectItem>
            <SelectItem value="false">No</SelectItem>
          </SelectContent>
        </Select>
      );
    }

    // Country / State / City → type-to-search location picker (stores the name),
    // rather than free text.
    const geoKind = GEO_KIND[draft.field];
    if (geoKind) {
      return (
        <AsyncEntitySelect
          value={draft.value || ""}
          label={draft.value || undefined}
          search={geoSearch[geoKind]}
          placeholder={GEO_PLACEHOLDER[geoKind]}
          onSelect={(name) => patchDraft({ value: name })}
        />
      );
    }

    // Date fields → calendar picker + relative-date chips. Travel Date also
    // offers week shortcuts (Current/Last Week).
    if (type === "date") {
      const chips = draft.field.endsWith("travel_date") ? TRAVEL_DATE_CHIPS : STANDARD_DATE_CHIPS;
      return (
        <DateFilterValue
          value={draft.value}
          onChange={(v) => patchDraft({ value: v })}
          chips={chips}
          arity={arity}
        />
      );
    }

    // Lookup / picklist fields → searchable pick from their values (never a raw
    // id box, and never an unsearchable wall of options).
    if (type === "lookup") {
      const options = optionsFor(draft.field);
      return (
        <SearchableSelect
          options={options.map((o) => ({ label: o.name, value: o.id }))}
          value={draft.value || ""}
          onValueChange={(v) => patchDraft({ value: v })}
          placeholder={options.length ? "Select…" : "Loading…"}
          searchPlaceholder="Search…"
          disabled={!options.length}
        />
      );
    }
    const inputType = type === "number" ? "number" : "text";
    if (arity === "two") {
      const arr = Array.isArray(draft.value) ? draft.value : ["", ""];
      return (
        <div className="flex items-center gap-1">
          <Input type={inputType} value={arr[0] ?? ""} onChange={(e) => patchDraft({ value: [e.target.value, arr[1] ?? ""] })} className="h-9 min-w-0 flex-1" />
          <span className="shrink-0 text-xs text-muted-foreground">to</span>
          <Input type={inputType} value={arr[1] ?? ""} onChange={(e) => patchDraft({ value: [arr[0] ?? "", e.target.value] })} className="h-9 min-w-0 flex-1" />
        </div>
      );
    }
    return <Input type={inputType} value={draft.value ?? ""} onChange={(e) => patchDraft({ value: e.target.value })} className="h-9" />;
  };

  const save = async () => {
    const filter_rules: FilterRule[] = rows
      .filter((r) => r.field && r.operator)
      .map((r) => {
        const type = fieldByKey.get(r.field)?.type ?? "string";
        const arity = operatorArityForType(type, r.operator);
        return arity === "none" ? { field: r.field, operator: r.operator } : { field: r.field, operator: r.operator, value: r.value };
      });
    setSaving(true);
    try {
      const updated = await entityViewsService.updateView(entity, view.id, { filter_rules, scope });
      toast.success("Filters saved");
      onSaved(updated);
      onOpenChange(false);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to save filters");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md">
        {/* Header — Cancel / Save (pr-12 clears the Sheet's built-in close X) */}
        <div className="flex items-center justify-between bg-primary px-4 py-3 pr-12 text-primary-foreground">
          <Button variant="secondary" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <SheetTitle className="text-sm font-semibold text-primary-foreground">Edit List Filters</SheetTitle>
          <Button variant="secondary" size="sm" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {/* Show me */}
          <div className="rounded-md bg-muted/40 p-3">
            <div className="text-xs text-muted-foreground">Show me</div>
            <div className="mt-1 font-medium">
              {SHOW_ME_LABEL[entity] ?? "All records"}
            </div>
          </div>

          {/* Committed filter rows */}
          {rows.map((row, i) => (
            <button
              key={i}
              type="button"
              onClick={() => openEdit(i)}
              className="flex w-full items-start justify-between rounded-md border p-3 text-left hover:bg-accent"
            >
              <div>
                <div className="text-sm font-medium">{fieldByKey.get(row.field)?.label || row.field}</div>
                <div className="text-xs text-muted-foreground">{summaryFor(row)}</div>
              </div>
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  removeRow(i);
                }}
                className="ml-2 text-muted-foreground hover:text-destructive"
                aria-label="Remove filter"
              >
                <X className="h-4 w-4" />
              </span>
            </button>
          ))}

          {/* Add Filter / Remove All */}
          <div className="flex items-center justify-between">
            <Button type="button" variant="link" className="h-auto p-0" onClick={openNew}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Add Filter
            </Button>
            {rows.length > 0 && (
              <Button type="button" variant="link" className="h-auto p-0 text-muted-foreground" onClick={removeAll}>
                Remove All
              </Button>
            )}
          </div>

          {/* Inline editor */}
          {editing !== null && draft && (
            <div className="space-y-3 rounded-md border p-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Fields</Label>
                <Select value={draft.field} onValueChange={onDraftField}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Field" /></SelectTrigger>
                  <SelectContent className="max-h-72">
                    <SelectGroup>
                      <SelectLabel className="border-b border-border bg-primary/10 px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-primary">Standard Fields</SelectLabel>
                      {coreStandard.map((f) => (
                        <SelectItem key={f.key} value={f.key}>{f.label}</SelectItem>
                      ))}
                    </SelectGroup>
                    {additional.length > 0 && (
                      <SelectGroup>
                        <SelectLabel className="mt-1 border-t border-border bg-primary/10 px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-primary">Additional Fields</SelectLabel>
                        {additional.map((f) => (
                          <SelectItem key={f.key} value={f.key}>{f.label}</SelectItem>
                        ))}
                      </SelectGroup>
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">Operator</Label>
                <Select value={draft.operator} onValueChange={(v) => patchDraft({ operator: v, value: "" })}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Operator" /></SelectTrigger>
                  <SelectContent>
                    {operatorsForType(fieldByKey.get(draft.field)?.type ?? "string").map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-muted-foreground">value</Label>
                {draftValueEditor()}
              </div>

              <div className="flex justify-end">
                <Button type="button" size="sm" onClick={commitDraft}>Done</Button>
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
