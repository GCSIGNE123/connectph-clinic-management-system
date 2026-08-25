"use client";

import { useRef, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useCommitTemplateImport,
  useDownloadBlankImportTemplate,
  usePreviewTemplateImport,
} from "@/features/laboratory/hooks/use-laboratory";
import type { LaboratoryTemplateImportPreview, LaboratoryTemplateImportResult } from "@/features/laboratory/types";

interface LaboratoryTemplateImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Bulk Laboratory Template maintenance: choose an `.xlsx` -> preview
 * (parse + validate, no DB writes) -> user confirms -> commit (one
 * transaction, re-validates independently). See
 * `laboratory_template_import_export.py`'s module docstring for the
 * two-sheet workbook format this drives. */
export function LaboratoryTemplateImportDialog({ open, onOpenChange }: LaboratoryTemplateImportDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<LaboratoryTemplateImportPreview | null>(null);
  const [result, setResult] = useState<LaboratoryTemplateImportResult | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const downloadBlank = useDownloadBlankImportTemplate();
  const previewMutation = usePreviewTemplateImport();
  const commitMutation = useCommitTemplateImport();

  function reset() {
    setFile(null);
    setPreview(null);
    setResult(null);
    setFileError(null);
  }

  function handleClose(nextOpen: boolean) {
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  }

  async function handleFileChosen(chosen: File | undefined) {
    setFileError(null);
    setPreview(null);
    setResult(null);
    if (!chosen) {
      setFile(null);
      return;
    }
    if (!chosen.name.toLowerCase().endsWith(".xlsx")) {
      setFile(null);
      setFileError("Please choose an .xlsx file.");
      return;
    }
    setFile(chosen);
    try {
      const nextPreview = await previewMutation.mutateAsync(chosen);
      setPreview(nextPreview);
    } catch {
      // usePreviewTemplateImport already toasts the error; the file stays
      // selected so the user can see what they picked and try again.
      setFileError("Could not read this file. Choose a valid exported/filled-in template workbook.");
    }
  }

  async function handleConfirm() {
    if (!file) return;
    const committed = await commitMutation.mutateAsync(file);
    setResult(committed);
    setPreview(null);
  }

  const isBusy = previewMutation.isPending || commitMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import Templates</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {!result ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" isLoading={downloadBlank.isPending} onClick={() => downloadBlank.mutate()}>
                  Download Excel Template
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx"
                  className="hidden"
                  onChange={(e) => {
                    void handleFileChosen(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
                <Button type="button" onClick={() => fileInputRef.current?.click()} isLoading={previewMutation.isPending}>
                  Choose .xlsx File
                </Button>
                {file ? <span className="text-sm text-muted-foreground">{file.name}</span> : null}
              </div>
              {fileError ? <p className="text-sm text-destructive">{fileError}</p> : null}

              {preview ? <ImportPreviewSummary preview={preview} /> : null}
            </>
          ) : (
            <ImportResultSummary result={result} />
          )}
        </div>

        <DialogFooter>
          {result ? (
            <Button type="button" onClick={() => handleClose(false)}>
              Close
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                Cancel
              </Button>
              <Button
                type="button"
                disabled={!preview || !preview.canCommit || isBusy}
                isLoading={commitMutation.isPending}
                onClick={handleConfirm}
              >
                Confirm Import
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ImportPreviewSummary({ preview }: { preview: LaboratoryTemplateImportPreview }) {
  return (
    <div className="space-y-3 rounded-md border border-border p-3">
      <h3 className="text-sm font-semibold text-foreground">Import Preview</h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
        <SummaryStat label="Templates" value={preview.templateCount} />
        <SummaryStat label="Parameters" value={preview.parameterCount} />
        <SummaryStat label="New templates" value={preview.newTemplateCount} />
        <SummaryStat label="Existing templates to update" value={preview.updatedTemplateCount} />
        <SummaryStat label="Errors" value={preview.errors.length} tone={preview.errors.length > 0 ? "error" : undefined} />
        <SummaryStat label="Warnings" value={preview.warnings.length} tone={preview.warnings.length > 0 ? "warning" : undefined} />
      </dl>

      {!preview.canCommit ? (
        <p className="text-sm text-destructive">Fix every error below before this import can be confirmed.</p>
      ) : null}

      {preview.diffs.length > 0 ? (
        <div className="space-y-2">
          {preview.diffs.map((diff) => (
            <div key={`${diff.templateId ?? "new"}-${diff.testName}`} className="rounded-sm border border-border/60 p-2 text-sm">
              <div className="flex items-center gap-2 font-medium text-foreground">
                {diff.testName}
                <Badge variant={diff.action === "create" ? "success" : "outline"}>{diff.action === "create" ? "New" : "Update"}</Badge>
              </div>
              <ul className="mt-1 space-y-0.5 text-xs">
                {diff.parameters.added.map((name) => (
                  <li key={`add-${name}`} className="text-emerald-700">+ {name}</li>
                ))}
                {diff.parameters.changed.map((name) => (
                  <li key={`chg-${name}`} className="text-amber-700">~ {name} changed</li>
                ))}
                {diff.parameters.removed.map((name) => (
                  <li key={`rem-${name}`} className="text-destructive">- {name} removed</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}

      {preview.errors.length > 0 ? <IssueList title="Errors" issues={preview.errors} tone="error" /> : null}
      {preview.warnings.length > 0 ? <IssueList title="Warnings" issues={preview.warnings} tone="warning" /> : null}
    </div>
  );
}

function SummaryStat({ label, value, tone }: { label: string; value: number; tone?: "error" | "warning" }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`text-base font-semibold ${tone === "error" ? "text-destructive" : tone === "warning" ? "text-amber-700" : "text-foreground"}`}>
        {value}
      </dd>
    </div>
  );
}

function IssueList({ title, issues, tone }: { title: string; issues: LaboratoryTemplateImportPreview["errors"]; tone: "error" | "warning" }) {
  return (
    <div>
      <h4 className={`text-xs font-semibold uppercase tracking-wide ${tone === "error" ? "text-destructive" : "text-amber-700"}`}>{title}</h4>
      <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
        {issues.map((issue, i) => (
          <li key={i}>
            <span className="font-medium uppercase">{tone}</span> — Sheet: {issue.sheet}, Row: {issue.row}
            {issue.template ? `, Template: ${issue.template}` : ""}
            {issue.parameter ? `, Parameter: ${issue.parameter}` : ""}
            <br />
            Reason: {issue.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ImportResultSummary({ result }: { result: LaboratoryTemplateImportResult }) {
  return (
    <div className="space-y-2 rounded-md border border-border p-3 text-sm">
      <p className="font-medium text-foreground">Import complete.</p>
      <p>{result.createdTemplateCount} template(s) created</p>
      <p>{result.updatedTemplateCount} template(s) updated</p>
      <p>{result.parameterCount} parameter(s) written</p>
      {result.templateNames.length > 0 ? (
        <p className="text-muted-foreground">{result.templateNames.join(", ")}</p>
      ) : null}
    </div>
  );
}
