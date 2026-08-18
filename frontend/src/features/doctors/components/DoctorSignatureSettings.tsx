"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { doctorSignatureApi } from "@/features/doctors/api/doctor-signature-api";
import type { Doctor } from "@/features/clinic-config/types";

/**
 * Doctor E-Signature settings section - one centralized capability reused
 * by Medical Certificate/Prescription/Referral printing (`DoctorSignatureBlock`),
 * not a per-document signature field. PNG only (product decision -
 * transparency, no compression artifacts on a legal document); supports
 * BOTH drawing directly in-browser and uploading an existing PNG.
 *
 * Permission is enforced by the backend (`require_doctor_signature_manage_role`
 * + `DoctorService.require_signature_manage_permission`'s ownership check) -
 * this component does not hide itself based on role, it surfaces whatever
 * the API actually allows/denies, so a Doctor viewing another doctor's page
 * sees a clear 403 message rather than a silently-disabled button that
 * could give a false impression of the real permission boundary.
 */
export function DoctorSignatureSettings({ doctor, onDoctorUpdated }: { doctor: Doctor; onDoctorUpdated: (doctor: Doctor) => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"idle" | "draw" | "upload">("idle");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasSignature = Boolean(doctor.signature_url);

  const previewQuery = useQuery({
    queryKey: ["doctor-signature-preview", doctor.id, doctor.signature_url],
    queryFn: () => doctorSignatureApi.getSignatureBlob(doctor.id),
    enabled: hasSignature,
    staleTime: Infinity,
    retry: false,
  });

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!previewQuery.data) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(previewQuery.data);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [previewQuery.data]);

  async function handleSaved(updated: Doctor) {
    setMode("idle");
    setError(null);
    await queryClient.invalidateQueries({ queryKey: ["doctor-signature-preview", doctor.id] });
    onDoctorUpdated(updated);
    toast({ title: hasSignature ? "Signature replaced." : "Signature saved.", variant: "success", durationMs: 3000 });
  }

  async function handleUploadFile(file: File) {
    if (file.type !== "image/png" && !file.name.toLowerCase().endsWith(".png")) {
      setError("Only PNG files are accepted.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await doctorSignatureApi.upload(doctor.id, file);
      await handleSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not upload signature.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove() {
    setSaving(true);
    setError(null);
    try {
      const updated = await doctorSignatureApi.remove(doctor.id);
      await queryClient.invalidateQueries({ queryKey: ["doctor-signature-preview", doctor.id] });
      onDoctorUpdated(updated);
      toast({ title: "Signature removed.", variant: "success", durationMs: 3000 });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove signature.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium">Current signature</h3>
        {hasSignature ? (
          previewQuery.isLoading ? (
            <p className="mt-2 text-sm text-muted-foreground">Loading preview…</p>
          ) : previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not a static/optimizable asset
            <img src={previewUrl} alt="Current signature" className="mt-2 h-24 w-56 rounded border border-border object-contain bg-white" />
          ) : (
            <p className="mt-2 text-sm text-destructive">Could not load the signature preview.</p>
          )
        ) : (
          <p className="mt-2 text-sm text-muted-foreground" data-testid="signature-not-configured">
            Signature not configured.
          </p>
        )}
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {mode === "idle" ? (
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={() => setMode("draw")} disabled={saving}>
            Draw Signature
          </Button>
          <Button type="button" variant="outline" onClick={() => setMode("upload")} disabled={saving}>
            Upload PNG
          </Button>
          {hasSignature ? (
            <Button type="button" variant="outline" className="text-destructive" onClick={handleRemove} disabled={saving}>
              Remove Signature
            </Button>
          ) : null}
        </div>
      ) : null}

      {mode === "upload" ? (
        <UploadPanel onCancel={() => setMode("idle")} onFile={handleUploadFile} saving={saving} />
      ) : null}

      {mode === "draw" ? (
        <DrawPanel onCancel={() => setMode("idle")} onFile={handleUploadFile} saving={saving} />
      ) : null}
    </div>
  );
}

function UploadPanel({ onCancel, onFile, saving }: { onCancel: () => void; onFile: (file: File) => void; saving: boolean }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <input
        ref={inputRef}
        type="file"
        accept="image/png,.png"
        className="block text-sm"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function DrawPanel({ onCancel, onFile, saving }: { onCancel: () => void; onFile: (file: File) => void; saving: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const [hasStroke, setHasStroke] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // Transparent background - PNG signatures commonly have none, matching
    // how they're meant to overlay on a printed document.
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.strokeStyle = "#111827";
  }, []);

  function pointerPos(e: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.setPointerCapture(e.pointerId);
    drawingRef.current = true;
    const ctx = canvas.getContext("2d")!;
    const { x, y } = pointerPos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  }

  function handlePointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    const { x, y } = pointerPos(e);
    ctx.lineTo(x, y);
    ctx.stroke();
    if (!hasStroke) setHasStroke(true);
  }

  function handlePointerUp() {
    drawingRef.current = false;
  }

  function handleClear() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx?.clearRect(0, 0, canvas.width, canvas.height);
    setHasStroke(false);
  }

  function handleSave() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      onFile(new File([blob], "signature.png", { type: "image/png" }));
    }, "image/png");
  }

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <canvas
        ref={canvasRef}
        width={400}
        height={150}
        className="w-full max-w-[400px] touch-none rounded border border-dashed border-border bg-white"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      />
      <div className="flex justify-between gap-2">
        <Button type="button" variant="outline" size="sm" onClick={handleClear} disabled={saving || !hasStroke}>
          Clear
        </Button>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
          <Button type="button" size="sm" onClick={handleSave} disabled={saving || !hasStroke}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </div>
  );
}
