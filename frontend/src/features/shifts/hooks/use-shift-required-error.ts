"use client";

import { useState, useCallback } from "react";
import { ApiError } from "@/lib/api-client";

/**
 * Item 7 (Shift Enforcement) - shared error-handling logic for the three
 * actions the backend now gates behind "Receptionist must have an open
 * shift" (`POST /queues`, appointment check-in, `POST
 * /invoices/{id}/payments`): all three surface the exact same 400 body
 * (`"Please start your shift before serving patients."`, see
 * `backend/app/services/shift_service.py::enforce_receptionist_open_shift`).
 *
 * Rather than duplicating "catch this specific error and show a Start
 * Shift prompt" in the Queue page, the check-in action, and the Payment
 * dialog, each caller wraps its mutation's `onError` with `handleError` from
 * this hook - if it recognizes the shift-required error it swallows it and
 * flips `open` to true (driving a shared `<ShiftRequiredDialog>`); for any
 * other error it returns `false` so the caller's own error handling
 * (toast, etc.) still runs.
 */
const SHIFT_REQUIRED_MESSAGE = "Please start your shift before serving patients.";

export function useShiftRequiredError() {
  const [open, setOpen] = useState(false);

  const handleError = useCallback((error: unknown): boolean => {
    if (error instanceof ApiError && error.statusCode === 400 && error.message.includes(SHIFT_REQUIRED_MESSAGE)) {
      setOpen(true);
      return true;
    }
    return false;
  }, []);

  return { open, setOpen, handleError };
}
