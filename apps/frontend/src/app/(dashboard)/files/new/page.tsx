"use client";

import { FileUploader } from "@/features/files/components/file-uploader";
import { Upload } from "lucide-react";
import { ModuleTitle } from "@/components/shared/module-title";

export default function NewFilePage() {
    return (
        <div className="flex-1 space-y-4 p-4 sm:p-8 pt-4 sm:pt-6">
            <div className="crm-surface flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <ModuleTitle icon={Upload} title="Upload File" description="Add a file to your Drive." />
            </div>
            <div className="rounded-md border p-4 max-w-xl">
                <FileUploader onUploadComplete={() => alert("File uploaded!")} />
            </div>
        </div>
    );
}
