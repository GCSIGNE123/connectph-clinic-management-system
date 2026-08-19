"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { billingApi } from "@/features/billing/api/billing-api";
import { useInvoice, useSyncInvoiceCache } from "@/features/billing/hooks/use-invoice";
import { PaymentDialog } from "@/features/billing/components/PaymentDialog";
import { ApiError } from "@/lib/api-client";
import type { Invoice } from "@/features/billing/types";

/**
 * Laboratory pay-first workflow: the "pay before queueing" step embedded
 * inside `NewQueueDialog`, for a draft Visit created via
 * `POST /visits/pre-queue` (status `DraftVitals`, no Queue ticket yet - same
 * precondition `PreQueueVitalsStep` builds on, just for Laboratory instead
 * of Consultation/Follow-up).
 *
 * Creates (idempotently) the Laboratory invoice for that visit, then reuses
 * the EXISTING `PaymentDialog`/`useRecordPayment` - no second payment system.
 * `onPaid` fires once the real invoice state (read from the shared billing
 * query cache, not inferred from department) reaches `Paid` - covers both
 * the normal "receptionist records a payment" path and the zero-priced
 * service edge case, where the backend marks the invoice `Paid` immediately
 * on creation and there is nothing to pay.
 */
export function LabPaymentStep({
  visitId,
  onPaid,
  onBack,
}: {
  visitId: string;
  onPaid: (invoiceId: string) => void;
  onBack: () => void;
}) {
  const [invoiceId, setInvoiceId] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(true);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const paidHandledRef = useRef(false);
  // React 18 dev-mode (StrictMode) mounts every effect twice (mount ->
  // cleanup -> mount again) for the SAME component instance, specifically to
  // surface missing-cleanup bugs. BUG-FIX (previously stuck on "Preparing
  // invoice..." forever): a closure-local `cancelled` flag combined with a
  // ref that only guarded RE-FIRING doesn't work here - StrictMode's first
  // effect invocation's cleanup marks ITS OWN `cancelled` true before the
  // real network response arrives, and the second invocation returns early
  // (via the ref guard) without ever attaching its own handler to that
  // response - so the successful result is silently discarded and nothing
  // ever calls `setPreparing(false)`. Fixed with a genuine single-flight
  // pattern instead: the in-flight/completed PROMISE itself (not just a
  // "did we start yet" boolean) is shared across every effect invocation
  // via a ref, so only one real network request is ever made, but EVERY
  // invocation that awaits it - including whichever one is still mounted
  // when it resolves - gets a chance to apply the result. Each invocation
  // still has its own `active` liveness flag so a truly unmounted/replaced
  // invocation doesn't call setState after the fact; the difference is the
  // flag is scoped per-invocation as intended, not leaked onto the one
  // invocation that's still current.
  const inFlightRef = useRef<{ visitId: string; promise: Promise<Invoice> } | null>(null);

  const syncInvoiceCache = useSyncInvoiceCache();
  const { data: invoice } = useInvoice(invoiceId);

  useEffect(() => {
    let active = true;

    async function prepareInvoice() {
      if (inFlightRef.current?.visitId !== visitId) {
        inFlightRef.current = { visitId, promise: billingApi.createLaboratoryInvoiceForVisit(visitId) };
      }
      const inFlight = inFlightRef.current;
      setPreparing(true);
      setPrepareError(null);
      try {
        const inv = await inFlight.promise;
        if (!active) return;
        syncInvoiceCache(inv);
        setInvoiceId(inv.id);
        if (inv.status !== "Paid") {
          setPaymentOpen(true);
        }
      } catch (err) {
        if (!active) return;
        // Requirement: if invoice creation fails, no queue is created - this
        // step simply never calls `onPaid`, and the receptionist can Back
        // out or retry from here without a queue ticket ever existing.
        // Clear the in-flight record so Retry (or a future mount) actually
        // re-attempts instead of re-awaiting the same failed promise.
        if (inFlightRef.current === inFlight) inFlightRef.current = null;
        setPrepareError(err instanceof ApiError ? err.message : "Could not create the Laboratory invoice.");
      } finally {
        if (active) setPreparing(false);
      }
    }

    void prepareInvoice();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visitId]);

  useEffect(() => {
    if (invoice && invoice.status === "Paid" && !paidHandledRef.current) {
      paidHandledRef.current = true;
      setPaymentOpen(false);
      onPaid(invoice.id);
    }
  }, [invoice, onPaid]);

  function handleRetryPrepare() {
    paidHandledRef.current = false;
    setInvoiceId(null);
    setPreparing(true);
    setPrepareError(null);
    const promise = billingApi.createLaboratoryInvoiceForVisit(visitId);
    inFlightRef.current = { visitId, promise };
    promise
      .then((inv) => {
        syncInvoiceCache(inv);
        setInvoiceId(inv.id);
        if (inv.status !== "Paid") setPaymentOpen(true);
      })
      .catch((err) => {
        if (inFlightRef.current?.promise === promise) inFlightRef.current = null;
        setPrepareError(err instanceof ApiError ? err.message : "Could not create the Laboratory invoice.");
      })
      .finally(() => setPreparing(false));
  }

  const labItem = invoice?.items.find((i) => i.itemType === "Laboratory") ?? invoice?.items[0];

  return (
    <div className="space-y-3">
      {preparing ? (
        <p className="text-sm text-muted-foreground">Preparing invoice...</p>
      ) : prepareError ? (
        <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <p>{prepareError}</p>
          <Button type="button" variant="outline" size="sm" onClick={handleRetryPrepare}>
            Retry
          </Button>
        </div>
      ) : invoice ? (
        <div className="space-y-2 rounded-md border border-border p-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Service</span>
            <span className="font-medium">{labItem?.description ?? "—"}</span>
          </div>
          <div className="flex justify-between text-base font-semibold">
            <span>Amount due</span>
            <span>₱{invoice.balanceDue.toFixed(2)}</span>
          </div>
          {invoice.status === "Paid" ? (
            <p className="text-xs font-medium text-green-600">Fully paid - creating the queue ticket...</p>
          ) : (
            <Button type="button" onClick={() => setPaymentOpen(true)}>
              Record Payment
            </Button>
          )}
        </div>
      ) : null}

      <div className="flex justify-between pt-2">
        {/* "Back", not "Cancel" - deliberately distinct from the reused
            PaymentDialog's own "Cancel" button (both can be on screen
            together), and matches this dialog's other step's ("Enter
            Vitals" via PreQueueVitalsStep) "Close" convention for
            returning to the main form without submitting anything. */}
        <Button type="button" variant="outline" onClick={onBack} disabled={preparing}>
          Back
        </Button>
      </div>

      {invoiceId && invoice ? (
        <PaymentDialog open={paymentOpen} onOpenChange={setPaymentOpen} invoiceId={invoiceId} balanceDue={invoice.balanceDue} />
      ) : null}
    </div>
  );
}
