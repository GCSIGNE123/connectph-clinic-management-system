"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_PRINT_PREFERENCES,
  PAPER_SIZES,
  type PaperSize,
  type PrintPreferences,
} from "@/features/print-settings/types";

const STORAGE_KEY = "connectph.printPreferences";

/**
 * Client Acceptance Revisions - Round 2, HIGH item 4: Printer Settings.
 *
 * Stored in `localStorage` (per browser/device, not per-clinic or per-user
 * account) - deliberately no backend model or migration. Two reasons:
 *
 * 1. "Default printer" is fundamentally a *client machine* concept - the
 *    printer physically attached to the front-desk PC has nothing to do
 *    with the clinic's server-side data, and a browser page has no API to
 *    query installed printers or pre-select one in the native print dialog
 *    (this is a deliberate, long-standing browser security restriction -
 *    `window.print()` always lets the OS dialog own printer selection).
 *    So we store the user's *stated preference* and simply display it back
 *    to them near the Print button ("Preferred printer: Front Desk HP
 *    LaserJet") - a reminder, not an actual selection mechanism.
 * 2. Paper size genuinely can be controlled from the page via the CSS
 *    `@page { size: ... }` at-rule, so that part of this setting is fully
 *    functional, not just a label.
 */
function readStoredPreferences(): PrintPreferences {
  if (typeof window === "undefined") return DEFAULT_PRINT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PRINT_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<PrintPreferences>;
    const paperSize = PAPER_SIZES.includes(parsed.paperSize as PaperSize)
      ? (parsed.paperSize as PaperSize)
      : DEFAULT_PRINT_PREFERENCES.paperSize;
    return {
      paperSize,
      defaultPrinterName:
        typeof parsed.defaultPrinterName === "string"
          ? parsed.defaultPrinterName
          : DEFAULT_PRINT_PREFERENCES.defaultPrinterName,
    };
  } catch {
    return DEFAULT_PRINT_PREFERENCES;
  }
}

/** Broadcasts preference changes to other mounted consumers in the same tab
 * (e.g. the Printer Settings page and an open print dialog) - `storage`
 * events only fire in *other* tabs/windows, not the one that wrote the key,
 * so same-tab consumers need a manual signal. */
const PREFERENCES_CHANGED_EVENT = "connectph:print-preferences-changed";

export function usePrintPreferences() {
  const [preferences, setPreferences] = useState<PrintPreferences>(DEFAULT_PRINT_PREFERENCES);

  useEffect(() => {
    setPreferences(readStoredPreferences());
    const handler = () => setPreferences(readStoredPreferences());
    window.addEventListener("storage", handler);
    window.addEventListener(PREFERENCES_CHANGED_EVENT, handler);
    return () => {
      window.removeEventListener("storage", handler);
      window.removeEventListener(PREFERENCES_CHANGED_EVENT, handler);
    };
  }, []);

  const update = useCallback((patch: Partial<PrintPreferences>) => {
    setPreferences((current) => {
      const next = { ...current, ...patch };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        window.dispatchEvent(new Event(PREFERENCES_CHANGED_EVENT));
      } catch {
        // localStorage unavailable (private browsing quota, etc.) - the
        // in-memory value still updates for this session.
      }
      return next;
    });
  }, []);

  return {
    preferences,
    setPaperSize: (paperSize: PaperSize) => update({ paperSize }),
    setDefaultPrinterName: (defaultPrinterName: string) => update({ defaultPrinterName }),
  };
}
