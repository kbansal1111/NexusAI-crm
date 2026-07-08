"use client";

import { useMemo } from "react";
import { useSession } from "next-auth/react";

/**
 * The single ergonomic primitive for permission-gating UI.
 *
 * Permissions are loaded into the encrypted NextAuth JWT at login (see
 * lib/auth.ts) and read here from the session with ZERO network calls, so
 * gating is instant on every render. The backend still enforces every action
 * (check_permission) — this only decides what UI to *show*, never what a user is
 * *allowed* to do. Hiding a button is UX; the server is the security boundary.
 *
 * Usage:
 *   const { can } = usePermissions();
 *   {can("create_opportunity") && <Button>New</Button>}
 *   <Button disabled={!can("edit_opportunity")} .../>
 *
 * For JSX-only wrapping, prefer <PermissionGate permission="..."> which uses the
 * same session under the hood.
 */
export function usePermissions() {
    const { data: session } = useSession();
    const permissions: string[] = (session?.user as any)?.permissions ?? [];
    // Memoise on the permission set's content so `can` is referentially stable
    // between renders unless the user's permissions actually change.
    const key = permissions.join(",");
    return useMemo(() => {
        const set = new Set(permissions);
        return {
            permissions,
            /** True if the user holds this exact permission. */
            can: (permission: string) => set.has(permission),
            /** True if the user holds ANY of these permissions. */
            canAny: (perms: string[]) => perms.some((p) => set.has(p)),
            /** True if the user holds ALL of these permissions. */
            canAll: (perms: string[]) => perms.every((p) => set.has(p)),
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]);
}
