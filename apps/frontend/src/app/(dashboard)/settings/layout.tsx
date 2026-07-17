"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Building2,
  Award,
  ListTree,
  UserCog,
  Mail,
  Map,
  CreditCard,
  Tags,
  ListChecks,
  ShieldCheck,
  Settings as SettingsIcon,
} from "lucide-react";
import { ReactNode } from "react";

const SECTIONS: { title: string; items: { href: string; label: string; icon: ReactNode }[] }[] = [
  {
    title: "Company",
    items: [
      { href: "/settings/company", label: "Company Profile", icon: <Building2 className="h-4 w-4" /> },
      { href: "/settings/leaderboard", label: "Leaderboard", icon: <Award className="h-4 w-4" /> },
      { href: "/settings/email-footer", label: "Email Footer", icon: <Mail className="h-4 w-4" /> },
    ],
  },
  {
    title: "Records & Fields",
    items: [
      { href: "/settings/custom-fields/lead", label: "Custom Fields", icon: <ListTree className="h-4 w-4" /> },
      { href: "/settings/standard-fields/lead", label: "Standard Fields", icon: <ListChecks className="h-4 w-4" /> },
      { href: "/settings/picklists/lead_status", label: "Picklists", icon: <Tags className="h-4 w-4" /> },
    ],
  },
  {
    title: "Routing & Org",
    items: [
      { href: "/settings/auto-assignment", label: "Auto-Assignment", icon: <UserCog className="h-4 w-4" /> },
      { href: "/settings/department-mapping", label: "Department Mapping", icon: <ShieldCheck className="h-4 w-4" /> },
      { href: "/settings/territory", label: "Territory", icon: <Map className="h-4 w-4" /> },
    ],
  },
  {
    title: "Billing",
    items: [
      { href: "/settings/billing", label: "Billing & Plans", icon: <CreditCard className="h-4 w-4" /> },
    ],
  },
];

function isActivePath(pathname: string, href: string) {
  // "/settings" itself redirects to /settings/company; exact-match it so no
  // item stays highlighted on every subpage if such a link is ever added back.
  if (href === "/settings") return pathname === "/settings";
  return pathname === href || pathname.startsWith(href + "/");
}

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex w-full flex-col lg:h-[calc(100vh-4rem)] lg:flex-row">
      {/* Desktop: fixed sidebar */}
      <aside className="hidden w-64 shrink-0 overflow-y-auto border-r bg-muted/30 p-4 lg:block">
        <div className="mb-4 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-chart-5 text-white shadow-sm">
            <SettingsIcon className="h-5 w-5" />
          </div>
          <span className="text-base font-bold tracking-tight">Settings</span>
        </div>
        <nav className="space-y-6">
          {SECTIONS.map((section) => (
            <div key={section.title}>
              <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {section.title}
              </div>
              <ul className="space-y-1">
                {section.items.map((item) => {
                  const active = isActivePath(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={cn(
                          "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
                          active
                            ? "bg-primary text-primary-foreground"
                            : "text-foreground hover:bg-muted",
                        )}
                      >
                        {item.icon}
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      {/* Mobile / tablet: stacked header + horizontally scrollable nav chips */}
      <div className="border-b bg-muted/30 px-3 py-2 lg:hidden">
        <div className="mb-2 flex items-center gap-2 px-1">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-chart-5 text-white shadow-sm">
            <SettingsIcon className="h-4 w-4" />
          </div>
          <span className="text-sm font-bold tracking-tight">Settings</span>
        </div>
        <nav className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
          {SECTIONS.flatMap((section) => section.items).map((item) => {
            const active = isActivePath(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium",
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-foreground hover:bg-muted",
                )}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <main className="min-w-0 flex-1 overflow-y-auto p-4 sm:p-6">{children}</main>
    </div>
  );
}
