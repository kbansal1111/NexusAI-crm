"use client";

import * as React from "react";
import { CalendarIcon } from "lucide-react";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";
import {
  isRelativeToken,
  RELATIVE_TOKEN_LABEL,
  type RelativeDateToken,
} from "./fieldMeta";

// Concrete date values are stored as plain "YYYY-MM-DD" strings (what the backend
// date clauses parse). Build/parse them from LOCAL calendar parts so the day a
// user clicks is the day that gets stored — never shifted by a UTC conversion.
function isoLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseLocal(iso?: string): Date | undefined {
  if (!iso) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return undefined;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

/** Single calendar-backed date field. `display` overrides the shown text (used
 *  to render a relative-token label in the same control). */
function CalendarPickButton({
  value,
  onPick,
  display,
  placeholder = "Choose a date",
}: {
  value: string;
  onPick: (iso: string) => void;
  display?: string;
  placeholder?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const selected = parseLocal(value);
  const text = display ?? (value ? formatDate(value) : "");
  return (
    <Popover open={open} onOpenChange={setOpen} modal>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          type="button"
          className={cn("h-9 w-full justify-between font-normal", !text && "text-muted-foreground")}
        >
          <span className="truncate">{text || placeholder}</span>
          <CalendarIcon className="ml-2 h-4 w-4 shrink-0 opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start" onPointerDownOutside={(e) => e.stopPropagation()}>
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          onSelect={(d) => {
            if (d) {
              onPick(isoLocal(d));
              setOpen(false);
            }
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

/**
 * Value editor for date filters. For single-value operators it offers a calendar
 * picker plus quick relative-date chips (Yesterday / Today / Current Month / …);
 * picking a calendar day stores a concrete date, a chip stores a relative token.
 * For "between" it shows two calendar pickers (no relative chips).
 */
export function DateFilterValue({
  value,
  onChange,
  chips,
  arity,
}: {
  value: any;
  onChange: (v: any) => void;
  chips: RelativeDateToken[];
  arity: "one" | "two";
}) {
  // Start expanded if the active token lives past the first two chips, so the
  // current selection is always visible when re-editing a saved filter.
  const [showAll, setShowAll] = React.useState(() => {
    const t = isRelativeToken(value) ? value : null;
    return t ? chips.indexOf(t) >= 2 : false;
  });

  if (arity === "two") {
    const arr = Array.isArray(value) ? value : ["", ""];
    return (
      <div className="flex items-center gap-1">
        <div className="min-w-0 flex-1">
          <CalendarPickButton value={arr[0] || ""} onPick={(v) => onChange([v, arr[1] || ""])} placeholder="Start date" />
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">to</span>
        <div className="min-w-0 flex-1">
          <CalendarPickButton value={arr[1] || ""} onPick={(v) => onChange([arr[0] || "", v])} placeholder="End date" />
        </div>
      </div>
    );
  }

  const token = isRelativeToken(value) ? value : null;
  const concrete = token ? "" : typeof value === "string" ? value : "";
  const visible = showAll ? chips : chips.slice(0, 2);

  return (
    <div className="space-y-2">
      <CalendarPickButton
        value={concrete}
        onPick={onChange}
        display={token ? RELATIVE_TOKEN_LABEL[token] : undefined}
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {visible.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => onChange(t)}
            className={cn("text-primary hover:underline", token === t && "font-semibold underline")}
          >
            {RELATIVE_TOKEN_LABEL[t]}
          </button>
        ))}
        {chips.length > 2 && (
          <button type="button" onClick={() => setShowAll((s) => !s)} className="text-primary hover:underline">
            {showAll ? "Less" : "More"}
          </button>
        )}
      </div>
    </div>
  );
}
