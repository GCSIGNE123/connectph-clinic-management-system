"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { migrationApi } from "@/features/migration/api/migration-api";
import { useMigrationBatches, useMigrationStatus, migrationKeys } from "@/features/migration/hooks/use-migration";
import { useQueryClient } from "@tanstack/react-query";
import type {
  MigrationBatch,
  MigrationEntityType,
  MigrationFieldMapping,
  MigrationMappingSuggestion,
  MigrationSourceType,
  MigrationValidationIssue,
} from "@/features/migration/types";
import { IMPLEMENTED_ENTITY_TYPES } from "@/features/migration/types";

const STEPS = ["Choose Source", "Connect", "Analyze", "Map Fields", "Preview", "Validate", "Import", "Verify"] as const;

const ALLOWED_ROLES = new Set(["Owner", "Administrator"]);

export default function MigrationWizardPage() {
  const { data: currentUser, isLoading: userLoading } = useCurrentUser();
  const { toast } = useToast();
  const qc = useQueryClient();

  const [step, setStep] = useState(0);
  const [sourceType, setSourceType] = useState<MigrationSourceType>("CSV");
  const [sourceDescription, setSourceDescription] = useState("");
  const [batch, setBatch] = useState<MigrationBatch | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [schema, setSchema] = useState<Record<string, string[]> | null>(null);
  const [entity, setEntity] = useState<MigrationEntityType>("Patients");
  const [mappings, setMappings] = useState<Record<MigrationEntityType, MigrationFieldMapping[]>>({} as Record<MigrationEntityType, MigrationFieldMapping[]>);
  const [issues, setIssues] = useState<MigrationValidationIssue[]>([]);
  const [preview, setPreview] = useState<{ rows_to_import: number; rows_to_skip: number; warnings: number; errors: number } | null>(null);
  const [importing, setImporting] = useState(false);

  const { data: history } = useMigrationBatches();
  const statusQuery = useMigrationStatus(batch && importing ? batch.id : null);
  const { data: verification } = useQuery({
    queryKey: batch ? [...migrationKeys.batch(batch.id), "verify"] : ["migration-verify-disabled"],
    queryFn: () => migrationApi.verify(batch!.id),
    enabled: Boolean(batch) && step === 7 && (statusQuery.data?.batch.status === "Completed" || statusQuery.data?.batch.status === "PartiallyCompleted"),
  });

  if (userLoading) return <div className="p-6 text-sm text-muted-foreground">Loading...</div>;
  if (!currentUser || !ALLOWED_ROLES.has(currentUser.role ?? "")) {
    return (
      <div className="p-6">
        <Card>
          <CardHeader>
            <CardTitle>Access restricted</CardTitle>
            <CardDescription>The Legacy Migration Wizard is available to Owner and Administrator roles only.</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  async function handleCreateBatch() {
    try {
      const created = await migrationApi.createBatch(sourceType, sourceDescription || undefined);
      setBatch(created);
      setStep(1);
      qc.invalidateQueries({ queryKey: migrationKeys.batches() });
    } catch (e) {
      toast({ title: "Failed to create batch", description: String(e), variant: "error" });
    }
  }

  async function handleUpload() {
    if (!batch || files.length === 0) return;
    try {
      const updated = await migrationApi.uploadFiles(batch.id, files);
      setBatch(updated);
      setStep(2);
    } catch (e) {
      toast({ title: "Upload failed", description: String(e), variant: "error" });
    }
  }

  async function handleAnalyze() {
    if (!batch) return;
    try {
      const result = await migrationApi.analyze(batch.id);
      setSchema(result);
      setStep(3);
      const firstEntity = Object.keys(result)[0] as MigrationEntityType | undefined;
      if (firstEntity) setEntity(firstEntity);
    } catch (e) {
      toast({ title: "Analyze failed", description: String(e), variant: "error" });
    }
  }

  async function loadSuggestions(entityType: MigrationEntityType) {
    if (!batch) return;
    const suggestions: MigrationMappingSuggestion[] = await migrationApi.suggestMappings(batch.id, entityType);
    setMappings((prev) => ({
      ...prev,
      [entityType]: suggestions.map((s, idx) => ({
        id: `local-${idx}`,
        entity_type: entityType,
        source_field: s.source_field,
        destination_field: s.destination_field,
        transform_type: "None",
        transform_config: null,
        is_ignored: s.is_ignored,
      })),
    }));
  }

  async function handleSaveMappingsAndContinue() {
    if (!batch || !schema) return;
    try {
      const all = Object.values(mappings).flat();
      await migrationApi.putMappings(batch.id, all.map((m) => ({
        entity_type: m.entity_type,
        source_field: m.source_field,
        destination_field: m.destination_field,
        transform_type: m.transform_type,
        transform_config: m.transform_config,
        is_ignored: m.is_ignored,
      })));
      setStep(4);
    } catch (e) {
      toast({ title: "Saving mappings failed", description: String(e), variant: "error" });
    }
  }

  async function handlePreview() {
    if (!batch || !schema) return;
    try {
      const entityTypes = Object.keys(schema) as MigrationEntityType[];
      let last = null;
      for (const et of entityTypes) {
        last = await migrationApi.preview(batch.id, et);
      }
      setPreview(last);
      setStep(5);
    } catch (e) {
      toast({ title: "Preview failed", description: String(e), variant: "error" });
    }
  }

  async function handleValidate() {
    if (!batch || !schema) return;
    try {
      const entityTypes = Object.keys(schema) as MigrationEntityType[];
      let allIssues: MigrationValidationIssue[] = [];
      for (const et of entityTypes) {
        const result = await migrationApi.validate(batch.id, et);
        allIssues = allIssues.concat(result);
      }
      setIssues(allIssues);
    } catch (e) {
      toast({ title: "Validation failed", description: String(e), variant: "error" });
    }
  }

  async function resolveIssue(issueId: string, resolution: string) {
    if (!batch) return;
    await migrationApi.resolveIssue(batch.id, issueId, resolution);
    setIssues((prev) => prev.map((i) => (i.id === issueId ? { ...i, resolution: resolution as MigrationValidationIssue["resolution"] } : i)));
  }

  async function handleStartImport() {
    if (!batch) return;
    if (!window.confirm("This will write real records into Patients/Doctors (and skip other entity types not yet implemented). Continue?")) return;
    try {
      await migrationApi.startImport(batch.id);
      setImporting(true);
      setStep(6);
    } catch (e) {
      toast({ title: "Import failed to start", description: String(e), variant: "error" });
    }
  }

  const unresolvedErrors = issues.filter((i) => i.severity === "Error" && (!i.resolution || i.resolution === "Unresolved"));

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Legacy Migration Wizard</h1>
        <p className="text-sm text-muted-foreground">Import patients and doctors from a legacy CSV/Excel export. Owner/Administrator only.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {STEPS.map((label, idx) => (
          <Badge key={label} variant={idx === step ? "default" : idx < step ? "secondary" : "outline"}>
            {idx + 1}. {label}
          </Badge>
        ))}
      </div>

      {step === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Step 1: Choose Source</CardTitle>
            <CardDescription>CSV and Excel are fully implemented. Other database sources are architecture-only in this build.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2">
              {(["CSV", "Excel", "SQLite", "Access", "SQLServer", "MySQL", "PostgreSQL"] as MigrationSourceType[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={s !== "CSV" && s !== "Excel"}
                  onClick={() => setSourceType(s)}
                  className={`rounded-md border p-3 text-left text-sm ${sourceType === s ? "border-primary bg-primary/5" : "border-border"} ${s !== "CSV" && s !== "Excel" ? "cursor-not-allowed opacity-50" : ""}`}
                >
                  <div className="font-medium">{s}</div>
                  <div className="text-xs text-muted-foreground">{s === "CSV" || s === "Excel" ? "Available" : "Coming soon"}</div>
                </button>
              ))}
            </div>
            <Input
              placeholder="Source description (e.g. filename or legacy system name)"
              value={sourceDescription}
              onChange={(e) => setSourceDescription(e.target.value)}
            />
            <Button onClick={handleCreateBatch}>Create migration batch</Button>
          </CardContent>
        </Card>
      )}

      {step === 1 && batch && (
        <Card>
          <CardHeader>
            <CardTitle>Step 2: Connect / Upload</CardTitle>
            <CardDescription>Upload one CSV file per entity (e.g. patients.csv, doctors.csv), or one Excel workbook.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <input
              type="file"
              multiple
              accept=".csv,.xlsx"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            <Button onClick={handleUpload} disabled={files.length === 0}>Upload</Button>
          </CardContent>
        </Card>
      )}

      {step === 2 && batch && (
        <Card>
          <CardHeader>
            <CardTitle>Step 3: Analyze</CardTitle>
            <CardDescription>Detect entity types and source columns from the uploaded file(s).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button onClick={handleAnalyze}>Analyze source</Button>
          </CardContent>
        </Card>
      )}

      {step === 3 && batch && schema && (
        <Card>
          <CardHeader>
            <CardTitle>Step 4: Map Fields</CardTitle>
            <CardDescription>Suggested mappings are pre-filled; adjust the destination field per source column.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2">
              <Select value={entity} onChange={(e) => { const v = e.target.value as MigrationEntityType; setEntity(v); if (!mappings[v]) loadSuggestions(v); }}>
                {Object.keys(schema).map((e) => (
                  <option key={e} value={e}>{e}{!IMPLEMENTED_ENTITY_TYPES.includes(e as MigrationEntityType) ? " (import not implemented - mapping only)" : ""}</option>
                ))}
              </Select>
              <Button variant="outline" onClick={() => loadSuggestions(entity)}>Suggest mappings</Button>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source field</TableHead>
                  <TableHead>Destination field</TableHead>
                  <TableHead>Ignore</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(mappings[entity] ?? []).map((m, idx) => (
                  <TableRow key={m.source_field}>
                    <TableCell>{m.source_field}</TableCell>
                    <TableCell>
                      <Input
                        value={m.destination_field ?? ""}
                        onChange={(ev) => {
                          const val = ev.target.value;
                          setMappings((prev) => ({
                            ...prev,
                            [entity]: prev[entity].map((row, i) => (i === idx ? { ...row, destination_field: val || null } : row)),
                          }));
                        }}
                      />
                    </TableCell>
                    <TableCell>
                      <input
                        type="checkbox"
                        checked={m.is_ignored}
                        onChange={(ev) => {
                          const checked = ev.target.checked;
                          setMappings((prev) => ({
                            ...prev,
                            [entity]: prev[entity].map((row, i) => (i === idx ? { ...row, is_ignored: checked } : row)),
                          }));
                        }}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Button onClick={handleSaveMappingsAndContinue}>Save mappings and continue</Button>
          </CardContent>
        </Card>
      )}

      {step === 4 && (
        <Card>
          <CardHeader>
            <CardTitle>Step 5: Preview</CardTitle>
            <CardDescription>Rows-to-import / rows-to-skip, computed without writing anything.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button onClick={handlePreview}>Compute preview</Button>
            {preview && (
              <div className="grid grid-cols-4 gap-4 text-center">
                <div><div className="text-2xl font-semibold">{preview.rows_to_import}</div><div className="text-xs text-muted-foreground">To import</div></div>
                <div><div className="text-2xl font-semibold">{preview.rows_to_skip}</div><div className="text-xs text-muted-foreground">To skip</div></div>
                <div><div className="text-2xl font-semibold">{preview.warnings}</div><div className="text-xs text-muted-foreground">Warnings</div></div>
                <div><div className="text-2xl font-semibold">{preview.errors}</div><div className="text-xs text-muted-foreground">Errors</div></div>
              </div>
            )}
            {preview && <Button onClick={() => setStep(5)}>Continue to Validate</Button>}
          </CardContent>
        </Card>
      )}

      {step === 5 && (
        <Card>
          <CardHeader>
            <CardTitle>Step 6: Validate & Resolve Issues</CardTitle>
            <CardDescription>Resolve each flagged row before import (Skip/Merge/Overwrite/CreateNew).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button onClick={handleValidate}>Run validation</Button>
            {issues.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Entity</TableHead>
                    <TableHead>Row</TableHead>
                    <TableHead>Issue</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Message</TableHead>
                    <TableHead>Resolution</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {issues.map((i) => (
                    <TableRow key={i.id}>
                      <TableCell>{i.entity_type}</TableCell>
                      <TableCell>{i.source_row_identifier}</TableCell>
                      <TableCell>{i.issue_type}</TableCell>
                      <TableCell><Badge variant={i.severity === "Error" ? "destructive" : "secondary"}>{i.severity}</Badge></TableCell>
                      <TableCell className="max-w-xs truncate">{i.message}</TableCell>
                      <TableCell>
                        <Select value={i.resolution ?? "Unresolved"} onChange={(ev) => resolveIssue(i.id, ev.target.value)}>
                          <option value="Unresolved">Unresolved</option>
                          <option value="Skip">Skip</option>
                          <option value="Merge">Merge</option>
                          <option value="Overwrite">Overwrite</option>
                          <option value="CreateNew">CreateNew</option>
                        </Select>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {unresolvedErrors.length > 0 && (
              <p className="text-sm text-destructive">{unresolvedErrors.length} unresolved error(s) - these rows will be skipped automatically during import unless resolved.</p>
            )}
            <Button onClick={handleStartImport}>Proceed to Import</Button>
          </CardContent>
        </Card>
      )}

      {step === 6 && batch && (
        <Card>
          <CardHeader>
            <CardTitle>Step 7: Migration Dashboard</CardTitle>
            <CardDescription>Live progress. Polls every 2 seconds while importing.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {statusQuery.data && (
              <>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat label="Status" value={statusQuery.data.batch.status} />
                  <Stat label="Source" value={statusQuery.data.batch.source_type} />
                  <Stat label="Found" value={String(statusQuery.data.batch.total_records_found ?? "-")} />
                  <Stat label="Imported" value={String(statusQuery.data.batch.total_records_imported)} />
                  <Stat label="Duplicates" value={String(statusQuery.data.batch.total_duplicates)} />
                  <Stat label="Warnings" value={String(statusQuery.data.batch.total_warnings)} />
                  <Stat label="Errors" value={String(statusQuery.data.batch.total_errors)} />
                  <Stat label="Elapsed" value={statusQuery.data.elapsed_seconds ? `${Math.round(statusQuery.data.elapsed_seconds)}s` : "-"} />
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Entity</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Found</TableHead>
                      <TableHead>Imported</TableHead>
                      <TableHead>Skipped</TableHead>
                      <TableHead>Failed</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {statusQuery.data.entities.map((e) => (
                      <TableRow key={e.entity_type}>
                        <TableCell>{e.entity_type}</TableCell>
                        <TableCell><Badge variant={e.status === "Completed" ? "secondary" : e.status === "Failed" ? "destructive" : "outline"}>{e.status}</Badge></TableCell>
                        <TableCell>{e.records_found}</TableCell>
                        <TableCell>{e.records_imported}</TableCell>
                        <TableCell>{e.records_skipped}</TableCell>
                        <TableCell>{e.records_failed}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {(statusQuery.data.batch.status === "Completed" || statusQuery.data.batch.status === "PartiallyCompleted") && (
                  <Button onClick={() => setStep(7)}>View Verification Report</Button>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}

      {step === 7 && verification && (
        <Card>
          <CardHeader>
            <CardTitle>Step 8: Verification Report</CardTitle>
            <CardDescription>Compares expected vs. imported counts per entity.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Badge variant={verification.overall_ok ? "secondary" : "destructive"}>
              {verification.overall_ok ? "All checks passed" : "Discrepancies found"}
            </Badge>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Entity</TableHead>
                  <TableHead>Expected</TableHead>
                  <TableHead>Imported</TableHead>
                  <TableHead>Match</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {verification.entities.filter((e) => e.expected > 0 || e.imported > 0).map((e) => (
                  <TableRow key={e.entity_type}>
                    <TableCell>{e.entity_type}</TableCell>
                    <TableCell>{e.expected}</TableCell>
                    <TableCell>{e.imported}</TableCell>
                    <TableCell>{e.matches ? "Yes" : "No"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Migration History</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Imported</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(history ?? []).map((b) => (
                <TableRow key={b.id}>
                  <TableCell>{b.source_type} - {b.source_description || "-"}</TableCell>
                  <TableCell><Badge variant="outline">{b.status}</Badge></TableCell>
                  <TableCell>{b.total_records_imported}</TableCell>
                  <TableCell>{new Date(b.created_at).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}
