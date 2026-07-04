/**
 * Canonical list-view field registry for every module that has the saved-view +
 * filter manager (account, personal_account, contact, lead, opportunity).
 *
 * Each module exposes its OWN standard fields (from the backend
 * DEFAULT_STANDARD_FIELDS + audit fields) — never another module's. This is the
 * source of truth for the "Edit List Filters" Fields dropdown and the
 * "Select Fields to display" picker. Custom/additional fields are appended
 * separately (and de-duped against standard via realCustomFields).
 *
 * Keep field keys in sync with the backend whitelist (app/core/entity_filter.py)
 * and each module's list-row shape.
 */
import type { LogicalType } from "./fieldMeta";
import type { EntityType } from "@/lib/api/services/field-registry.service";
import { SEGMENT_OPTIONS } from "@/lib/segments";

// Segment filter options, derived from the canonical segment list so B2C / B2B /
// Corporate stay in sync with src/lib/segments.ts (never hardcode the subset).
const SEGMENT_FILTER_OPTIONS: { id: string; name: string }[] = SEGMENT_OPTIONS.map(
  ({ value, label }) => ({ id: value, name: label }),
);

export interface ViewFieldDef {
  key: string;
  label: string;
  type: LogicalType;
}

const AUDIT_FIELDS: ViewFieldDef[] = [
  { key: "created_at", label: "Created Date", type: "date" },
  { key: "updated_at", label: "Last Modified Date", type: "date" },
  { key: "created_by", label: "Created By", type: "lookup" },
  { key: "owner_id", label: "Owner", type: "lookup" },
  { key: "last_modified_by_id", label: "Last Modified By", type: "lookup" },
];

export const ACCOUNT_STANDARD_FIELDS: ViewFieldDef[] = [
  { key: "name", label: "Account Name", type: "string" },
  { key: "phone", label: "Phone", type: "string" },
  { key: "email", label: "Email", type: "string" },
  { key: "billing_street", label: "Billing Street", type: "string" },
  { key: "billing_city", label: "Billing City", type: "string" },
  { key: "billing_state", label: "Billing State", type: "string" },
  { key: "billing_zip", label: "Billing Zip", type: "string" },
  { key: "billing_country", label: "Billing Country", type: "string" },
  { key: "acc_type_id", label: "Account Type", type: "lookup" },
  { key: "acc_parent_id", label: "Account Parent", type: "lookup" },
  { key: "website", label: "Website", type: "string" },
  { key: "category_id", label: "Category", type: "lookup" },
  { key: "industry_id", label: "Industry", type: "lookup" },
  { key: "created_at", label: "Created Date", type: "date" },
  { key: "updated_at", label: "Last Modified Date", type: "date" },
  { key: "created_by", label: "Created By", type: "lookup" },
  { key: "owner_id", label: "Owner", type: "lookup" },
  { key: "last_modified_by_id", label: "Last Modified By", type: "lookup" },
  { key: "id", label: "Account ID", type: "string" },
];

export const PERSONAL_ACCOUNT_STANDARD_FIELDS: ViewFieldDef[] = [
  { key: "salutation", label: "Salutation", type: "lookup" },
  { key: "first_name", label: "First Name", type: "string" },
  { key: "last_name", label: "Last Name", type: "string" },
  { key: "email", label: "Email", type: "string" },
  { key: "phone", label: "Phone", type: "string" },
  { key: "mobile", label: "Mobile", type: "string" },
  { key: "billing_street", label: "Billing Street", type: "string" },
  { key: "billing_city", label: "Billing City", type: "string" },
  { key: "billing_state", label: "Billing State", type: "string" },
  { key: "billing_zip", label: "Billing Zip", type: "string" },
  { key: "billing_country", label: "Billing Country", type: "string" },
  { key: "category_id", label: "Category", type: "lookup" },
  { key: "created_at", label: "Created Date", type: "date" },
  { key: "updated_at", label: "Last Modified Date", type: "date" },
  { key: "created_by", label: "Created By", type: "lookup" },
  { key: "owner_id", label: "Owner", type: "lookup" },
  { key: "last_modified_by_id", label: "Last Modified By", type: "lookup" },
  { key: "id", label: "Person Account ID", type: "string" },
];

export const CONTACT_STANDARD_FIELDS: ViewFieldDef[] = [
  { key: "salutation", label: "Salutation", type: "lookup" },
  { key: "first_name", label: "First Name", type: "string" },
  { key: "last_name", label: "Last Name", type: "string" },
  { key: "email", label: "Email", type: "string" },
  { key: "phone", label: "Phone", type: "string" },
  { key: "mobile", label: "Mobile", type: "string" },
  { key: "title", label: "Job Title", type: "string" },
  { key: "account_id", label: "Account", type: "lookup" },
  // Mailing address — mirrors the contact form's "Address Information" section.
  { key: "mailing_street", label: "Mailing Street", type: "string" },
  { key: "mailing_city", label: "Mailing City", type: "string" },
  { key: "mailing_state", label: "Mailing State", type: "string" },
  { key: "mailing_zip", label: "Mailing Zip", type: "string" },
  { key: "mailing_country", label: "Mailing Country", type: "string" },
  ...AUDIT_FIELDS,
  { key: "id", label: "Contact ID", type: "string" },
];

export const LEAD_STANDARD_FIELDS: ViewFieldDef[] = [
  { key: "salutation", label: "Salutation", type: "lookup" },
  { key: "first_name", label: "First Name", type: "string" },
  { key: "last_name", label: "Last Name", type: "string" },
  { key: "company", label: "Company", type: "string" },
  { key: "email", label: "Email", type: "string" },
  { key: "phone", label: "Phone", type: "string" },
  { key: "mobile", label: "Mobile", type: "string" },
  { key: "no_employees", label: "No. of Employees", type: "number" },
  { key: "website", label: "Website", type: "string" },
  { key: "title", label: "Title / Designation", type: "string" },
  { key: "lead_status_id", label: "Lead Status", type: "lookup" },
  { key: "source_id", label: "Source", type: "lookup" },
  { key: "industry_id", label: "Industry", type: "lookup" },
  { key: "street", label: "Street", type: "string" },
  { key: "city", label: "City", type: "string" },
  { key: "state", label: "State", type: "string" },
  { key: "zip", label: "Zip / Postal Code", type: "string" },
  { key: "country", label: "Country", type: "string" },
  { key: "custom_fields.campaign_name", label: "Campaign Name", type: "string" },
  { key: "custom_fields.segment", label: "Segment", type: "lookup" },
  { key: "custom_fields.experience_id", label: "Experience", type: "lookup" },
  { key: "custom_fields.ip_address", label: "IP Address", type: "string" },
  { key: "creation_type", label: "Creation Type", type: "lookup" },
  { key: "industry_data.travel_date", label: "Travel Date", type: "date" },
  { key: "industry_data.destination_ids", label: "Destination(s)", type: "lookup" },
  { key: "industry_data.no_of_pax", label: "No. of Pax", type: "number" },
  { key: "industry_data.no_of_nights", label: "No. of Nights", type: "number" },
  { key: "industry_data.no_of_adults", label: "No. of Adults", type: "number" },
  { key: "industry_data.no_of_childs", label: "No. of Children", type: "number" },
  { key: "industry_data.no_of_infants", label: "No. of Infants", type: "number" },
  ...AUDIT_FIELDS,
  { key: "id", label: "Lead ID", type: "string" },
];

export const OPPORTUNITY_STANDARD_FIELDS: ViewFieldDef[] = [
  { key: "name", label: "Opportunity Name", type: "string" },
  { key: "amount", label: "Amount", type: "number" },
  { key: "sales_stage_id", label: "Sales Stage", type: "lookup" },
  { key: "probability", label: "Probability (%)", type: "number" },
  { key: "opportunity_type_id", label: "Opportunity Type", type: "lookup" },
  { key: "source_id", label: "Source", type: "lookup" },
  { key: "segment", label: "Segment", type: "lookup" },
  { key: "creation_type", label: "Creation Type", type: "lookup" },
  { key: "close_date", label: "Close Date", type: "date" },
  { key: "account_id", label: "Account", type: "lookup" },
  { key: "contact_id", label: "Contact", type: "lookup" },
  { key: "close_lost_reason", label: "Close Lost Reason", type: "string" },
  { key: "industry_data.travel_date", label: "Travel Date", type: "date" },
  { key: "industry_data.destination_ids", label: "Destination(s)", type: "lookup" },
  { key: "industry_data.no_of_pax", label: "No. of Pax", type: "number" },
  { key: "custom_fields.starting_city", label: "Starting City", type: "string" },
  ...AUDIT_FIELDS,
  { key: "id", label: "Opportunity ID", type: "string" },
];

// Mirrors the Supplier form exactly: every filterable field here is a field the
// user can actually set on the form (and vice-versa). Form-only display fields
// that have no input (company_name / website / payment_terms / rating /
// is_preferred) were removed so the filter no longer offers fields the form
// can't produce.
export const SUPPLIER_STANDARD_FIELDS: ViewFieldDef[] = [
  { key: "name", label: "Supplier Name", type: "string" },
  { key: "supplier_type", label: "Supplier Type", type: "lookup" },
  { key: "contact_person_name", label: "Contact Person", type: "string" },
  { key: "email", label: "Email", type: "string" },
  { key: "phone", label: "Phone", type: "string" },
  { key: "mobile", label: "Mobile", type: "string" },
  { key: "services", label: "Service(s)", type: "string" },
  // Service Area (multi-select name arrays on the form) — geo-picker filters.
  { key: "countries", label: "Service Area Country", type: "string" },
  { key: "states", label: "Service Area State", type: "string" },
  { key: "service_cities", label: "Service Area City", type: "string" },
  { key: "destinations", label: "Destination(s)", type: "lookup" },
  // Billing address (labels match the form's "Address Information" section).
  { key: "street", label: "Billing Street", type: "string" },
  { key: "city", label: "Billing City", type: "string" },
  { key: "state", label: "Billing State", type: "string" },
  { key: "zip", label: "Billing Zip", type: "string" },
  { key: "country", label: "Billing Country", type: "string" },
  { key: "created_at", label: "Created Date", type: "date" },
  { key: "updated_at", label: "Last Modified Date", type: "date" },
  { key: "created_by", label: "Created By", type: "lookup" },
  { key: "owner_id", label: "Owner", type: "lookup" },
  { key: "id", label: "Supplier ID", type: "string" },
];

export const TASK_STANDARD_FIELDS: ViewFieldDef[] = [
  { key: "name", label: "Subject", type: "string" },
  { key: "status", label: "Status", type: "lookup" },
  { key: "priority", label: "Priority", type: "lookup" },
  { key: "due_date", label: "Due Date", type: "date" },
  { key: "assigned_user_id", label: "Assigned To", type: "lookup" },
  { key: "account_id", label: "Account", type: "lookup" },
  { key: "contact_id", label: "Contact", type: "lookup" },
  { key: "created_at", label: "Created Date", type: "date" },
  { key: "updated_at", label: "Last Modified Date", type: "date" },
  { key: "created_by", label: "Created By", type: "lookup" },
  { key: "owner_id", label: "Owner", type: "lookup" },
  { key: "id", label: "Task ID", type: "string" },
];

const CATALOGS: Partial<Record<EntityType, ViewFieldDef[]>> = {
  account: ACCOUNT_STANDARD_FIELDS,
  personal_account: PERSONAL_ACCOUNT_STANDARD_FIELDS,
  contact: CONTACT_STANDARD_FIELDS,
  lead: LEAD_STANDARD_FIELDS,
  opportunity: OPPORTUNITY_STANDARD_FIELDS,
  supplier: SUPPLIER_STANDARD_FIELDS,
  task: TASK_STANDARD_FIELDS,
};

export function standardFieldsFor(entity: EntityType): ViewFieldDef[] {
  return CATALOGS[entity] || ACCOUNT_STANDARD_FIELDS;
}

export function standardFieldByKey(entity: EntityType): Map<string, ViewFieldDef> {
  const m = new Map<string, ViewFieldDef>();
  standardFieldsFor(entity).forEach((f) => m.set(f.key, f));
  return m;
}

// ── "Additional Information" fields ──────────────────────────────────────────
// Catalog fields a module's form groups under its "Additional Information"
// heading. They stay real, filterable catalog fields, but the column picker
// lists them under "Available Additional Fields" (and hides them from "Available
// Standard Fields") so the picker mirrors the form. Extend per module as a
// form's "Additional Information" section gains fields.
export const ADDITIONAL_FIELD_KEYS_BY_ENTITY: Record<string, string[]> = {
  // Mirrors the Lead form's "Additional Information" section (Segment / Campaign /
  // IP Address / Experience). These live in the lead's custom_fields dict.
  lead: ["custom_fields.segment", "custom_fields.campaign_name", "custom_fields.ip_address", "custom_fields.experience_id"],
  opportunity: ["custom_fields.starting_city", "close_lost_reason"],
};

export function additionalFieldKeysFor(entity: EntityType): Set<string> {
  return new Set(ADDITIONAL_FIELD_KEYS_BY_ENTITY[entity] || []);
}

// ── Default visible columns (used when a view has no explicit display_columns,
// and to seed the "Select Fields to display" picker) ────────────────────────
export const DEFAULT_COLUMNS_BY_ENTITY: Record<string, string[]> = {
  account: ["name", "phone", "billing_street", "acc_type_id", "owner_id"],
  personal_account: ["first_name", "last_name", "email", "phone", "mobile", "owner_id"],
  contact: ["first_name", "last_name", "email", "phone", "mobile", "account_id", "owner_id"],
  lead: ["first_name", "last_name", "email", "phone", "city", "lead_status_id", "custom_fields.segment", "source_id"],
  opportunity: ["name", "amount", "account_id", "sales_stage_id", "close_date", "owner_id"],
  supplier: ["name", "supplier_type", "phone", "email", "owner_id"],
  task: ["name", "status", "priority", "due_date", "assigned_user_id"],
};

export function defaultColumnsFor(entity: EntityType): string[] {
  return DEFAULT_COLUMNS_BY_ENTITY[entity] || DEFAULT_COLUMNS_BY_ENTITY.account;
}

// ── Reference (server-search) fields, by the entity collection they target ───
const ACCOUNT_REF_BY_ENTITY: Record<string, string[]> = {
  account: ["acc_parent_id"],
  contact: ["account_id"],
  opportunity: ["account_id"],
  task: ["account_id"],
};
const CONTACT_REF_BY_ENTITY: Record<string, string[]> = {
  opportunity: ["contact_id"],
  task: ["contact_id"],
};
export function accountRefFieldsFor(entity: EntityType): Set<string> {
  return new Set(ACCOUNT_REF_BY_ENTITY[entity] || []);
}
export function contactRefFieldsFor(entity: EntityType): Set<string> {
  return new Set(CONTACT_REF_BY_ENTITY[entity] || []);
}

// ── Lookup value option sources ──────────────────────────────────────────────
// field_key -> key in the metadata "bundle" each table already has loaded.
const LOOKUP_OPTIONS_KEY_BY_ENTITY: Record<string, Record<string, string>> = {
  account: {
    owner_id: "users", created_by: "users", last_modified_by_id: "users",
    acc_type_id: "account_types", industry_id: "industries", category_id: "categories",
  },
  personal_account: {
    owner_id: "users", created_by: "users", last_modified_by_id: "users", category_id: "categories",
    salutation: "salutations",
  },
  contact: {
    owner_id: "users", created_by: "users", last_modified_by_id: "users",
    salutation: "salutations",
  },
  lead: {
    owner_id: "users", created_by: "users", last_modified_by_id: "users",
    lead_status_id: "lead_statuses", source_id: "sources",
    industry_id: "industries",
    "industry_data.destination_ids": "destinations",
    "custom_fields.experience_id": "experiences", salutation: "salutations",
  },
  opportunity: {
    owner_id: "users", created_by: "users", last_modified_by_id: "users",
    sales_stage_id: "sales_stages", opportunity_type_id: "opportunity_types",
    source_id: "sources", "industry_data.destination_ids": "destinations",
  },
  supplier: {
    owner_id: "users", created_by: "users", supplier_type: "supplier_types",
  },
  task: {
    owner_id: "users", created_by: "users", assigned_user_id: "users",
    status: "task_statuses", priority: "task_priorities",
  },
};

// Fixed-option selects (no metadata source).
const STATIC_OPTIONS_BY_ENTITY: Record<string, Record<string, { id: string; name: string }[]>> = {
  lead: {
    "custom_fields.segment": SEGMENT_FILTER_OPTIONS,
    creation_type: [{ id: "manual", name: "Manual" }, { id: "auto", name: "Auto" }, { id: "import", name: "Import" }],
  },
  opportunity: {
    segment: SEGMENT_FILTER_OPTIONS,
    creation_type: [{ id: "Manual", name: "Manual" }, { id: "Auto", name: "Auto" }],
  },
};

export type OptionList = { id: string; name: string }[];

/**
 * Build a field_key → options map for the filter value dropdowns, from the
 * metadata bundle a table already holds (users, picklists, …). Async reference
 * fields (accounts/contacts) are intentionally excluded — those use search.
 */
export function buildLookupOptions(
  entity: EntityType,
  bundle: Record<string, OptionList | undefined>,
): Record<string, OptionList> {
  const out: Record<string, OptionList> = {};
  const map = LOOKUP_OPTIONS_KEY_BY_ENTITY[entity] || {};
  for (const [field, bundleKey] of Object.entries(map)) {
    if (bundle[bundleKey]) out[field] = bundle[bundleKey] as OptionList;
  }
  for (const [field, opts] of Object.entries(STATIC_OPTIONS_BY_ENTITY[entity] || {})) {
    out[field] = opts;
  }
  return out;
}

/**
 * Genuine custom fields only. Some tenants (migrated from the legacy CRM) carry
 * additional-field records that duplicate standard fields (e.g. "Account Name",
 * "Email"). Those must NOT appear under "Custom Fields" — drop any whose label
 * or key collides with a standard field (case-insensitive), incl. prefix
 * aliases like "Account Owner" → "Owner".
 */
export function realCustomFields<T extends { label?: string | null; name: string; field_key?: string }>(
  entity: EntityType,
  fields: T[],
): T[] {
  const taken = new Set<string>();
  standardFieldsFor(entity).forEach((f) => {
    taken.add(f.label.toLowerCase());
    taken.add(f.key.toLowerCase());
  });
  const strip = (s: string) => s.replace(/^(account|person account)\s+/, "").trim();
  const isTaken = (s: string) => !!s && (taken.has(s) || taken.has(strip(s)));
  return fields.filter((f) => {
    const label = (f.label || f.name || "").trim().toLowerCase();
    const name = (f.name || "").trim().toLowerCase();
    const key = (f.field_key || "").trim().toLowerCase();
    return !isTaken(label) && !isTaken(name) && !isTaken(key);
  });
}
