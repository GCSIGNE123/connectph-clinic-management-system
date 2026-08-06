"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { patientApiFetch, PatientApiError } from "@/features/patient-portal/api/client";
import { cancelAppointment, getAvailableSlots, rescheduleAppointment, TimeSlot } from "@/features/patient-portal/api/appointments";

interface Appt {
  id: string; appointment_number: string; appointment_type: string; appointment_date: string;
  start_time: string; end_time: string; status: string; doctor_name: string | null;
  department_name: string | null; notes: string | null;
  doctor_id?: string | null;
}

const TABS = ["upcoming", "completed", "cancelled", "rescheduled"] as const;

// Statuses a patient may still act on (reschedule/cancel) - mirrors the
// staff-side `APPOINTMENT_STATUS_TRANSITIONS` allowing Rescheduled/Cancelled
// only from Booked/Confirmed (see `models/appointment.py`).
const ACTIONABLE_STATUSES = new Set(["Booked", "Confirmed"]);

export default function AppointmentsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("upcoming");
  const [rows, setRows] = useState<Appt[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [reschedulingId, setReschedulingId] = useState<string | null>(null);
  const [rescheduleDate, setRescheduleDate] = useState("");
  const [rescheduleSlots, setRescheduleSlots] = useState<TimeSlot[] | null>(null);
  const [rescheduleTime, setRescheduleTime] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    setRows(null);
    patientApiFetch<Appt[]>(`/patient-portal/appointments?tab=${tab}`).then(setRows).catch((e) => setError(e.message));
  }

  useEffect(load, [tab]);

  async function handleCancel(id: string) {
    setActionError(null);
    setBusy(true);
    try {
      await cancelAppointment(id, "Cancelled by patient via patient portal");
      load();
    } catch (e) {
      setActionError(e instanceof PatientApiError ? e.message : "Failed to cancel appointment.");
    } finally {
      setBusy(false);
    }
  }

  async function loadRescheduleSlots(doctorId: string | null | undefined, date: string) {
    setRescheduleSlots(null);
    setRescheduleTime("");
    if (!doctorId || !date) return;
    try {
      const r = await getAvailableSlots(doctorId, date);
      setRescheduleSlots(r.slots);
    } catch (e) {
      setActionError(e instanceof PatientApiError ? e.message : "Failed to load available times.");
    }
  }

  async function handleConfirmReschedule(id: string) {
    if (!rescheduleDate || !rescheduleTime) return;
    setActionError(null);
    setBusy(true);
    try {
      await rescheduleAppointment(id, { appointment_date: rescheduleDate, start_time: rescheduleTime, reason: "Rescheduled by patient" });
      setReschedulingId(null);
      load();
    } catch (e) {
      setActionError(e instanceof PatientApiError ? e.message : "Failed to reschedule appointment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Appointments</h1>
        <Link
          href="/patient-portal/appointments/book"
          style={{
            padding: "8px 14px", borderRadius: 8, background: "#0f766e", color: "#fff", fontSize: 13,
            textDecoration: "none", fontWeight: 600,
          }}
        >
          + Book Appointment
        </Link>
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "6px 12px", borderRadius: 999, border: "1px solid #cbd5e1", fontSize: 12, cursor: "pointer",
              background: tab === t ? "#0f766e" : "#fff", color: tab === t ? "#fff" : "#334155", textTransform: "capitalize",
            }}
          >
            {t}
          </button>
        ))}
      </div>
      {error && <div style={{ color: "#dc2626" }}>{error}</div>}
      {actionError && <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{actionError}</div>}
      {!rows && !error && <div>Loading...</div>}
      {rows && rows.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No appointments in this category.</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rows?.map((a) => (
          <div key={a.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{a.appointment_type} - {a.appointment_number}</div>
            <div style={{ fontSize: 13, color: "#475569" }}>
              {a.appointment_date} {a.start_time}-{a.end_time} | Dr. {a.doctor_name ?? "TBD"} | {a.department_name ?? "-"}
            </div>
            <div style={{ fontSize: 12, color: "#0f766e", marginTop: 4 }}>{a.status}</div>

            {ACTIONABLE_STATUSES.has(a.status) && (
              <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                <button
                  disabled={busy}
                  onClick={() => {
                    setReschedulingId(reschedulingId === a.id ? null : a.id);
                    setRescheduleDate("");
                    setRescheduleSlots(null);
                    setRescheduleTime("");
                  }}
                  style={{ fontSize: 12, padding: "5px 10px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer" }}
                >
                  Reschedule
                </button>
                <button
                  disabled={busy}
                  onClick={() => handleCancel(a.id)}
                  style={{ fontSize: 12, padding: "5px 10px", borderRadius: 6, border: "1px solid #fecaca", background: "#fff", color: "#dc2626", cursor: "pointer" }}
                >
                  Cancel
                </button>
              </div>
            )}

            {reschedulingId === a.id && (
              <div style={{ marginTop: 10, padding: 10, background: "#f8fafc", borderRadius: 8 }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    type="date"
                    value={rescheduleDate}
                    min={new Date().toISOString().slice(0, 10)}
                    onChange={(e) => {
                      setRescheduleDate(e.target.value);
                      loadRescheduleSlots(a.doctor_id, e.target.value);
                    }}
                    style={{ padding: 6, borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
                  />
                  <select
                    value={rescheduleTime}
                    onChange={(e) => setRescheduleTime(e.target.value)}
                    disabled={!rescheduleSlots || rescheduleSlots.length === 0}
                    style={{ padding: 6, borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
                  >
                    <option value="">Select time</option>
                    {rescheduleSlots?.map((s) => (
                      <option key={s.start_time} value={s.start_time}>
                        {s.start_time.slice(0, 5)}
                      </option>
                    ))}
                  </select>
                  <button
                    disabled={busy || !rescheduleDate || !rescheduleTime}
                    onClick={() => handleConfirmReschedule(a.id)}
                    style={{ fontSize: 12, padding: "6px 10px", borderRadius: 6, border: "none", background: "#0f766e", color: "#fff", cursor: "pointer" }}
                  >
                    Confirm New Time
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
