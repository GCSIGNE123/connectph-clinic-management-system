/**
 * Patient-initials derivation - mirrors the backend's server-side logic
 * (`app/services/tv_display_service.py::_initials`) exactly, so the same
 * privacy rule ("initials only, never full name") is documented and
 * testable on both sides. The public display always receives
 * already-derived initials from the API; this client-side copy exists for
 * the admin preview panel and to keep the rule unit-tested independently
 * of a live backend.
 */
export function deriveInitials(firstName: string, lastName: string): string {
  const f = firstName?.trim()?.[0]?.toUpperCase() ?? "";
  const l = lastName?.trim()?.[0]?.toUpperCase() ?? "";
  const initials = `${f}${l}`;
  return initials || "??";
}

/**
 * TTS announcement text templating - architecture only (Phase 13 spec: no
 * real audio synthesis). Mirrors `backend/app/services/tts_service.py`'s
 * `generate_announcement_text` string-formatting behavior so the same
 * template can be previewed client-side before saving a display config.
 */
export function formatTtsTemplate(
  template: string | null | undefined,
  values: { queueNumber: string; room?: string | null; doctor?: string | null; patientInitials?: string | null }
): string {
  const tpl = template && template.trim().length > 0 ? template : "Queue {queue_number}, please proceed to {room}.";
  return tpl
    .replaceAll("{queue_number}", values.queueNumber)
    .replaceAll("{room}", values.room || "the counter")
    .replaceAll("{doctor}", values.doctor || "")
    .replaceAll("{patient_initials}", values.patientInitials || "");
}
