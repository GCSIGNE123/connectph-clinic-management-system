"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

/**
 * Generic e-signature settings panel: draw-in-browser or upload PNG,
 * preview, replace, remove. Round 6 (Laboratory Report Signatories)
 * generalization of `features/doctors/components/DoctorSignatureSettings.tsx`
 * (the original, still-untouched Doctor E-Signature implementation) into a
 * shared component - same UX, parameterized by the caller's own
 * upload/remove/fetch-blob API calls instead of being hard-wired to
 * `doctorSignatureApi`. Used by both the Med Tech In Charge signature
 * section (Profile page, self-service) and the Pathologist signature
 * section (Pathologists master-data page, Owner/Administrator-managed) so
 * neither reinvents the draw/upload/preview/remove flow or its PNG-only
 * validation.
 */
export function SignaturePanel({
  hasSignature,
  previewQueryKey,
  getBlob,
  upload,
  remove,
  onChanged,
}: {
  hasSignature: boolean;
  /** react-query cache key for the preview blob - invalidated after every change. */
  previewQueryKey: unknown[];
  getBlob: () => Promise<Blob>;
  upload: (file: File) => Promise<void>;
  remove: () => Promise<void>;
  /** Called after a successful upload/remove, once the preview cache has
   * already been invalidated - use it to refetch the owning record. */
  onChanged?: () => void;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"idle" | "draw" | "upload">("idle");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const previewQuery = useQuery({
    queryKey: previewQueryKey,
    queryFn: getBlob,
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

  async function handleSaved() {
    setMode("idle");
    setError(null);
    await queryClient.invalidateQueries({ queryKey: previewQueryKey });
    onChanged?.();
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
      await upload(file);
      await handleSaved();
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
      await remove();
      await queryClient.invalidateQueries({ queryKey: previewQueryKey });
      onChanged?.();
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
