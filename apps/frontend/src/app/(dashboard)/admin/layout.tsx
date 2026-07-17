"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Users, ShieldCheck, ListTree, Shield } from "lucide-react";
import { ReactNode } from "react";
import { usePermissions } from "@/hooks/use-permissions";

const SECTIONS: {
  title: string;
  items: { href: string; label: string; icon: ReactNode; requiredPermission: string }[];
}[] = [
  {
    title: "Team & Access",
    items: [
      {
        href: "/admin/users",
        label: "Users",
        icon: <Users className="h-4 w-4" />,
        requiredPermission: "view_user",
      },
      {
        href: "/admin/role-management",
        label: "Profiles & Permissions",
        icon: <ShieldCheck className="h-4 w-4" />,
        requiredPermission: "view_role",
      },
      {
        href: "/admin/hierarchies",
        label: "Roles",
        icon: <ListTree className="h-4 w-4" />,
        requiredPermission: "view_hierarchy",
      },
    ],
  },
];

function isActivePath(pathname: string, href: string) {
  if (href === "/admin") return pathname === "/admin";
  return pathname === href || pathname.startsWith(href + "/");
}

export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { can } = usePermissions();

  const sections = SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => can(item.requiredPermission)),
  })).filter((section) => section.items.length > 0);

  return (
    <div className="flex w-full flex-col lg:h-[calc(100vh-4rem)] lg:flex-row">
      {/* Desktop: fixed sidebar */}
      <aside className="hidden w-64 shrink-0 overflow-y-auto border-r bg-muted/30 p-4 lg:block">
        <div className="mb-4 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-chart-5 text-white shadow-sm">
            <Shield className="h-5 w-5" />
          </div>
          <span className="text-base font-bold tracking-tight">Admin</span>
        </div>
        <nav className="space-y-6">
          {sections.map((section) => (
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
            <Shield className="h-4 w-4" />
          </div>
          <span className="text-sm font-bold tracking-tight">Admin</span>
        </div>
        <nav className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
          {sections.flatMap((section) => section.items).map((item) => {
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

      {/* Admin pages carry their own crm-page padding — don't double-pad here. */}
      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
