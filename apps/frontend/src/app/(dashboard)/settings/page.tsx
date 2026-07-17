import { redirect } from "next/navigation";

// The settings sidebar (layout.tsx) already lists every section — a card-grid
// overview here just duplicated it. Land on Company Profile instead.
export default function SettingsLanding() {
  redirect("/settings/company");
}
