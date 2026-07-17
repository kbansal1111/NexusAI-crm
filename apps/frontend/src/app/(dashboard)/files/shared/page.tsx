"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  filesExtraService,
  type FileShare,
  type FileFolder,
} from "@/lib/api/services/files-extra.service";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, FolderOpen, FileText, Share2 } from "lucide-react";
import { formatDate } from "@/lib/format";
import { ModuleTitle } from "@/components/shared/module-title";

export default function SharedFilesPage() {
  return (
    <div className="p-4 sm:p-6 max-w-5xl space-y-4">
      <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <ModuleTitle
          icon={Share2}
          title="Shared with me"
          description="Files and folders other users have shared with you."
        />
      </div>
      <Tabs defaultValue="files">
        <TabsList>
          <TabsTrigger value="files">Files</TabsTrigger>
          <TabsTrigger value="folders">Folders</TabsTrigger>
          <TabsTrigger value="admin">By admin</TabsTrigger>
        </TabsList>
        <TabsContent value="files">
          <FilesTab />
        </TabsContent>
        <TabsContent value="folders">
          <FoldersTab />
        </TabsContent>
        <TabsContent value="admin">
          <AdminTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function FilesTab() {
  const [rows, setRows] = useState<FileShare[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    filesExtraService
      .sharedWithMe()
      .then(setRows)
      .catch(() => toast.error("Load failed"))
      .finally(() => setLoading(false));
  }, []);
  if (loading)
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  if (!rows.length)
    return (
      <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
        No files shared with you.
      </div>
    );
  return (
    <ul className="space-y-1">
      {rows.map((r) => (
        <li key={r.id} className="flex items-center gap-2 rounded-md border p-2">
          <FileText className="h-4 w-4" />
          <span className="font-mono text-xs">{r.file_id || r.folder_id}</span>
          <span className="ml-auto text-xs text-muted-foreground">
            {r.permission} · {formatDate(r.shared_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function FoldersTab() {
  const [rows, setRows] = useState<FileFolder[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    filesExtraService
      .foldersSharedWithMe()
      .then(setRows)
      .catch(() => toast.error("Load failed"))
      .finally(() => setLoading(false));
  }, []);
  if (loading)
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  if (!rows.length)
    return (
      <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
        No folders shared with you.
      </div>
    );
  return (
    <ul className="space-y-1">
      {rows.map((r) => (
        <li key={r.id} className="flex items-center gap-2 rounded-md border p-2">
          <FolderOpen className="h-4 w-4 text-amber-600" />
          <span className="font-medium">{r.name}</span>
          {r.description && (
            <span className="text-xs text-muted-foreground">{r.description}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function AdminTab() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    filesExtraService
      .sharedByAdmin()
      .then(setRows)
      .catch(() => toast.error("Load failed"))
      .finally(() => setLoading(false));
  }, []);
  if (loading)
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  if (!rows.length)
    return (
      <div className="rounded-md border border-dashed p-8 text-center text-muted-foreground">
        No admin-shared resources.
      </div>
    );
  return (
    <ul className="space-y-1">
      {rows.map((r, i) => (
        <li key={i} className="rounded-md border p-2 font-mono text-xs">
          {JSON.stringify(r)}
        </li>
      ))}
    </ul>
  );
}
