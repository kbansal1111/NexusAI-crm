"use client";

import { useSession } from "next-auth/react";
import { hasPermission } from "@/lib/rbac";
import { AssistantPanel } from "./AssistantPanel";

/** Assistant covers opportunities, leads, and accounts — show the launcher when
 *  the user can view ANY of them. Per-tool RBAC narrows access server-side. */
const ASSISTANT_VIEW_PERMISSIONS = ["view_opportunity", "view_lead", "view_account"];

export function AssistantGate() {
    const { data: session } = useSession();
    const perms = (session?.user as any)?.permissions as string[] | undefined;
    if (!ASSISTANT_VIEW_PERMISSIONS.some((p) => hasPermission(perms, p))) return null;
    return <AssistantPanel />;
}
