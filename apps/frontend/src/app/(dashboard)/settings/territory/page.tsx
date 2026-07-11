"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { territoryService, type Territory } from "@/lib/api/services/territory.service";
import { usersExtraService } from "@/lib/api/services/users-extra.service";
import { Button } from "@/components/ui/button";
import { Loader2, Plus, Pencil, Trash2, FlaskConical } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { TerritoryFormDialog } from "@/features/bd/settings/components/TerritoryFormDialog";
import { TerritoryAssignmentTester } from "@/features/bd/settings/components/TerritoryAssignmentTester";

// Simplified territory management (mirrors the client's legacy CRM):
// one table — Name / Countries / States / Destinations — and one Add/Edit form.
export default function TerritoryPage() {
  const [rows, setRows] = useState<Territory[]>([]);
  const [userNames, setUserNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Territory | null>(null);
  const [open, setOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [showTester, setShowTester] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const t = await territoryService.listTerritories();
      setRows(t.territories);
    } catch {
      toast.error("Load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    usersExtraService
      .getAllActive()
      .then((data: any) => {
        const arr = Array.isArray(data) ? data : data?.users || [];
        const map: Record<string, string> = {};
        for (const u of arr) map[u.id || u._id] = u.name;
        setUserNames(map);
      })
      .catch(() => {});
  }, [reload]);

  const onDelete = async () => {
    if (!deleteId) return;
    try {
      await territoryService.deleteTerritory(deleteId);
      toast.success("Territory deleted");
      reload();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Delete failed");
    } finally {
      setDeleteId(null);
    }
  };

  const joined = (vals?: string[]) => (vals && vals.length ? vals.join(", ") : "—");

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Territories</h1>
          <p className="text-sm text-muted-foreground">
            A territory defines the countries/states a BD user covers. Assign territories to
            a BD user on the Admin &rarr; Users form; the owner is shown here read-only.
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setOpen(true);
          }}
        >
          <Plus className="h-4 w-4 mr-1" /> New
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
          No territories yet. Click &ldquo;New&rdquo; to add the first one.
        </div>
      ) : (
        <div className="rounded-md border overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/30 text-left">
              <tr>
                <th className="px-3 py-2 w-16">Sr. No.</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Countries</th>
                <th className="px-3 py-2">States</th>
                <th className="px-3 py-2">Destinations</th>
                <th className="px-3 py-2">BD User</th>
                <th className="px-3 py-2 w-24 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t, i) => (
                <tr key={t.id} className="border-b last:border-b-0 align-top">
                  <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
                  <td className="px-3 py-2 font-medium whitespace-nowrap">{t.name}</td>
                  <td className="px-3 py-2">{joined(t.countries)}</td>
                  <td className="px-3 py-2">{joined(t.states)}</td>
                  <td className="px-3 py-2">{joined(t.destinations)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {t.manager_id ? userNames[t.manager_id] || "Assigned" : "—"}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => {
                        setEditing(t);
                        setOpen(true);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" onClick={() => setDeleteId(t.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="pt-2">
        <Button variant="ghost" size="sm" onClick={() => setShowTester((v) => !v)}>
          <FlaskConical className="h-4 w-4 mr-1" />
          {showTester ? "Hide assignment test" : "Test which territory an address maps to"}
        </Button>
        {showTester && (
          <div className="mt-2">
            <TerritoryAssignmentTester />
          </div>
        )}
      </div>

      <TerritoryFormDialog
        open={open}
        onOpenChange={setOpen}
        territory={editing}
        onSaved={reload}
      />
      <AlertDialog open={!!deleteId} onOpenChange={(v) => !v && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete territory?</AlertDialogTitle>
            <AlertDialogDescription>
              The BD user will stop seeing this territory&apos;s opportunities. Existing
              opportunities are not deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
