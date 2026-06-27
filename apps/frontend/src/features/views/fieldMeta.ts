/**
 * Shared metadata for the list-view filter builder & field picker.
 *
 * Mirrors the backend's logical field types and operator set
 * (app/core/entity_filter.py). Keep the two in sync.
 */

export type LogicalType = "string" | "lookup" | "bool" | "number" | "date";

/** Map a StandardField/AdditionalField `field_type` to a logical filter type. */
export function logicalType(fieldType: string | null | undefined): LogicalType {
  switch ((fieldType || "text").toLowerCase()) {
    case "lookup":
      return "lookup";
    case "boolean":
    case "checkbox":
      return "bool";
    case "number":
    case "currency":
      return "number";
    case "date":
    case "datetime":
      return "date";
    default:
      // text, email, phone, url, textarea, select, multiselect, …
      return "string";
  }
}

export interface OperatorDef {
  value: string;
  label: string;
  /** false = no value input (e.g. is empty); "two" = range (between). */
  arity: "one" | "two" | "none";
}

// Operator sets are intentionally lean (per product spec):
//   • text     → equals / not equal to
//   • number   → equals / not equal to / less than / greater than / between
//   • date     → equals / not equal to / less than / greater than / between
//   • lookup   → is / is not (+ empty checks)
// Legacy saved views may still carry older operators (contains, is_empty, …);
// the backend continues to honor those, they're just no longer offered here.
export const OPERATORS_BY_TYPE: Record<LogicalType, OperatorDef[]> = {
  string: [
    { value: "equals", label: "equals", arity: "one" },
    { value: "not_equals", label: "not equal to", arity: "one" },
  ],
  lookup: [
    { value: "equals", label: "equals", arity: "one" },
    { value: "not_equals", label: "not equal to", arity: "one" },
  ],
  bool: [
    { value: "equals", label: "equals", arity: "one" },
    { value: "not_equals", label: "not equal to", arity: "one" },
  ],
  number: [
    { value: "equals", label: "equals", arity: "one" },
    { value: "not_equals", label: "not equal to", arity: "one" },
    { value: "less_than", label: "less than", arity: "one" },
    { value: "greater_than", label: "greater than", arity: "one" },
    { value: "between", label: "between", arity: "two" },
  ],
  date: [
    { value: "equals", label: "equals", arity: "one" },
    { value: "not_equals", label: "not equal to", arity: "one" },
    { value: "less_than", label: "less than", arity: "one" },
    { value: "greater_than", label: "greater than", arity: "one" },
    { value: "between", label: "between", arity: "two" },
  ],
};

export function operatorsFor(fieldType: string | null | undefined): OperatorDef[] {
  return OPERATORS_BY_TYPE[logicalType(fieldType)];
}

/** Operators for an already-resolved logical type (catalog fields). */
export function operatorsForType(lt: LogicalType): OperatorDef[] {
  return OPERATORS_BY_TYPE[lt];
}

export function operatorArityForType(
  lt: LogicalType,
  operator: string,
): "one" | "two" | "none" {
  return OPERATORS_BY_TYPE[lt].find((o) => o.value === operator)?.arity ?? "one";
}

export function operatorArity(
  fieldType: string | null | undefined,
  operator: string,
): "one" | "two" | "none" {
  return operatorsFor(fieldType).find((o) => o.value === operator)?.arity ?? "one";
}

// ── Relative date literals ───────────────────────────────────────────────────
// A date filter's value may be a *relative* token instead of a concrete date, so
// a saved view ("Leads created yesterday") stays correct over time. The backend
// resolves these to day ranges at query time (app/core/entity_filter.py —
// keep the token set in sync).
export const RELATIVE_DATE_TOKENS = [
  "TODAY",
  "YESTERDAY",
  "TOMORROW",
  "CURRENT_WEEK",
  "LAST_WEEK",
  "CURRENT_MONTH",
  "PREVIOUS_MONTH",
] as const;

export type RelativeDateToken = (typeof RELATIVE_DATE_TOKENS)[number];

const RELATIVE_TOKEN_SET = new Set<string>(RELATIVE_DATE_TOKENS);

export function isRelativeToken(v: unknown): v is RelativeDateToken {
  return typeof v === "string" && RELATIVE_TOKEN_SET.has(v);
}

export const RELATIVE_TOKEN_LABEL: Record<RelativeDateToken, string> = {
  TODAY: "Today",
  YESTERDAY: "Yesterday",
  TOMORROW: "Tomorrow",
  CURRENT_WEEK: "Current Week",
  LAST_WEEK: "Last Week",
  CURRENT_MONTH: "Current Month",
  PREVIOUS_MONTH: "Previous Month",
};

// Quick-pick chip sets. Standard date fields (Created/Modified/Close/Due) offer
// day + month shortcuts; Travel Date additionally offers week shortcuts.
export const STANDARD_DATE_CHIPS: RelativeDateToken[] = [
  "YESTERDAY",
  "TODAY",
  "TOMORROW",
  "CURRENT_MONTH",
  "PREVIOUS_MONTH",
];

export const TRAVEL_DATE_CHIPS: RelativeDateToken[] = [
  "YESTERDAY",
  "TODAY",
  "TOMORROW",
  "CURRENT_WEEK",
  "LAST_WEEK",
  "CURRENT_MONTH",
  "PREVIOUS_MONTH",
];
