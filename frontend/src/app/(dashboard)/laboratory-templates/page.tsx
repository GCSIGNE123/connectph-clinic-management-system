"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { EmptyState } from "@/components/layout/EmptyState";
import { useLaboratoryTemplates } from "@/features/laboratory/hooks/use-laboratory";
import { LaboratoryTemplateFormDialog } from "@/features/laboratory/components/LaboratoryTemplateFormDialog";
import type { LaboratoryTemplate } from "@/features/laboratory/types";

/** Administrator-only test-catalog configuration screen (Phase 10) - lives
 * under Clinic Configuration conceptually but is its own top-level route
 * since it isn't part of the shared `MasterDataPage` config array. */
export default function LaboratoryTemplatesPage() {
  const { data: templates, isLoading } = useLaboratoryTemplates();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<LaboratoryTemplate | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Laboratory Test Templates</h1>
          <p className="text-sm text-muted-foreground">Configure tests, parameters, pricing, and turnaround times.</p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setDialogOpen(true);
          }}
        >
          + New Template
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Templates</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4">
              <SkeletonList rows={4} />
            </div>
          ) : templates && templates.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                    <th className="px-3 py-2">Test</th>
                    <th className="px-3 py-2">Category</th>
                    <th className="px-3 py-2">Specimen</th>
                    <th className="px-3 py-2">Price</th>
                    <th className="px-3 py-2">Turnaround</th>
                    <th className="px-3 py-2">Parameters</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {templates.map((t) => (
                    <tr key={t.id} className="border-b border-border/50 last:border-0">
                      <td className="px-3 py-2 font-medium">{t.testName}</td>
                      <td className="px-3 py-2 text-muted-foreground">{t.testCategory ?? "-"}</td>
                      <td className="px-3 py-2 text-muted-foreground">{t.specimenType ?? "-"}</td>
                      <td className="px-3 py-2">₱{t.defaultPrice.toFixed(2)}</td>
                      <td className="px-3 py-2 text-muted-foreground">{t.turnaroundTimeHours ? `${t.turnaroundTimeHours}h` : "-"}</td>
                      <td className="px-3 py-2 text-muted-foreground">{t.parameters.length}</td>
                      <td className="px-3 py-2">
                        <Badge variant={t.isActive ? "success" : "outline"}>{t.isActive ? "Active" : "Inactive"}</Badge>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditing(t);
                            setDialogOpen(true);
                          }}
                        >
                          Edit
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No test templates yet" description="Create a template so doctors and the lab can select configured tests." />
          )}
        </CardContent>
      </Card>

      <LaboratoryTemplateFormDialog open={dialogOpen} onOpenChange={setDialogOpen} template={editing} />
    </div>
  );
}
