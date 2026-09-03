"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import type { FieldConfig } from "@/features/clinic-config/components/FieldConfig";

interface MasterDataFormDialogProps<T> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  record: T | null;
  fields: FieldConfig[];
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void;
}

/** Generic create/edit form dialog driven by a `FieldConfig[]` - see MasterDataPage. */
export function MasterDataFormDialog<T extends Record<string, unknown>>({
  open,
  onOpenChange,
  record,
  fields,
  onSubmit,
}: MasterDataFormDialogProps<T>) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    const initial: Record<string, unknown> = {};
    fields.forEach((field) => {
      initial[field.name] = record ? (record as Record<string, unknown>)[field.name] ?? "" : field.type === "checkbox" ? false : "";
    });
    setValues(initial);
  }, [open, record, fields]);

  const visibleFields = fields.filter((f) => !f.hidden && !(record && f.createOnly));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{record ? "Edit record" : "Add record"}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setSubmitting(true);
            try {
              // Empty optional text/select fields are tracked as "" for controlled
              // inputs, but the backend schemas treat unset optional fields as
              // absent/null, not an empty string (e.g. `EmailStr | None` rejects
              // ""). Normalize before sending.
              const payload = Object.fromEntries(
                Object.entries(values).map(([key, value]) => {
                  if (value !== "") return [key, value];
                  const field = fields.find((f) => f.name === key);
                  return [key, field?.nullable ? null : undefined];
                })
              );
              await onSubmit(payload);
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <div className="grid max-h-[60vh] gap-4 overflow-y-auto pr-1">
            {visibleFields.map((field) => (
              <div key={field.name} className="space-y-1.5">
                <Label htmlFor={field.name}>
                  {field.label}
                  {field.required ? " *" : ""}
                </Label>
                {field.type === "textarea" ? (
                  <Textarea
                    id={field.name}
                    value={(values[field.name] as string) ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                    placeholder={field.placeholder}
                  />
                ) : field.type === "select" ? (
                  <Select
                    id={field.name}
                    value={(values[field.name] as string) ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                  >
                    {/* Skip the generic placeholder when the field already
                        supplies its own "" option (e.g. `nullable`'s
                        "Unassigned") - otherwise the select would show two
                        empty-value options and always display the generic
                        one instead of the field's own meaningful label. */}
                    {field.options?.some((opt) => opt.value === "") ? null : <option value="">Select...</option>}
                    {field.options?.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </Select>
                ) : field.type === "checkbox" ? (
                  <Checkbox
                    id={field.name}
                    checked={Boolean(values[field.name])}
                    onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.checked }))}
                  />
                ) : (
                  <Input
                    id={field.name}
                    type={field.type === "number" ? "number" : field.type === "time" ? "time" : field.type === "date" ? "date" : field.type === "color" ? "color" : "text"}
                    value={(values[field.name] as string) ?? ""}
                    required={field.required}
                    placeholder={field.placeholder}
                    onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                  />
                )}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={submitting}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
