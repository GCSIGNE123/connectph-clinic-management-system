"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  APPOINTMENT_TYPES,
  BranchOption,
  DepartmentOption,
  DoctorOption,
  TimeSlot,
  createAppointment,
  getAvailableDates,
  getAvailableSlots,
  listBranches,
  listDepartments,
  listDoctors,
} from "@/features/patient-portal/api/appointments";
import { PatientApiError } from "@/features/patient-portal/api/client";

// Step order per spec: Branch -> Department -> Doctor -> Type -> Date -> Time -> Confirm.
const STEPS = ["Branch", "Department", "Doctor", "Type", "Date", "Time", "Confirm"] as const;
type Step = (typeof STEPS)[number];

const card: React.CSSProperties = { background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16 };
const button: React.CSSProperties = {
  padding: "8px 14px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer", fontSize: 13,
};
const primaryButton: React.CSSProperties = { ...button, background: "#0f766e", color: "#fff", border: "none" };
const optionRow: React.CSSProperties = {
  padding: "10px 12px", border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 8, cursor: "pointer", fontSize: 13,
};
const optionRowSelected: React.CSSProperties = { ...optionRow, borderColor: "#0f766e", background: "#f0fdfa" };

function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function BookAppointmentPage() {
  const router = useRouter();
  const [stepIndex, setStepIndex] = useState(0);
  const step: Step = STEPS[stepIndex];

  const [branches, setBranches] = useState<BranchOption[] | null>(null);
  const [departments, setDepartments] = useState<DepartmentOption[] | null>(null);
  const [doctors, setDoctors] = useState<DoctorOption[] | null>(null);
  const [availableDates, setAvailableDates] = useState<string[] | null>(null);
  const [slots, setSlots] = useState<TimeSlot[] | null>(null);

  const [branchId, setBranchId] = useState<string | null>(null);
  const [departmentId, setDepartmentId] = useState<string | null>(null);
  const [doctorId, setDoctorId] = useState<string | null>(null);
  const [appointmentType, setAppointmentType] = useState<string | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [startTime, setStartTime] = useState<string | null>(null);
  const [notes, setNotes] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [booked, setBooked] = useState<{ appointment_number: string } | null>(null);

  useEffect(() => {
    listBranches().then(setBranches).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (step === "Department" && departments === null) {
      listDepartments().then(setDepartments).catch((e) => setError(e.message));
    }
    if (step === "Doctor" && branchId) {
      listDoctors({ branchId, departmentId: departmentId ?? undefined }).then(setDoctors).catch((e) => setError(e.message));
    }
    if (step === "Date" && doctorId) {
      const today = new Date();
      const to = new Date();
      to.setDate(to.getDate() + 45);
      getAvailableDates(doctorId, fmtDate(today), fmtDate(to), branchId ?? undefined)
        .then((r) => setAvailableDates(r.dates))
        .catch((e) => setError(e.message));
    }
    if (step === "Time" && doctorId && date) {
      getAvailableSlots(doctorId, date, branchId ?? undefined)
        .then((r) => setSlots(r.slots))
        .catch((e) => setError(e.message));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  function goNext() {
    setError(null);
    setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
  }
  function goBack() {
    setError(null);
    setStepIndex((i) => Math.max(i - 1, 0));
  }

  async function handleConfirm() {
    if (!branchId || !doctorId || !appointmentType || !date || !startTime) return;
    setSubmitting(true);
    setError(null);
    try {
      const detail = await createAppointment({
        branch_id: branchId, doctor_id: doctorId, department_id: departmentId, appointment_type: appointmentType,
        appointment_date: date, start_time: startTime, notes: notes || null,
      });
      setBooked({ appointment_number: detail.appointment_number });
    } catch (e) {
      const msg = e instanceof PatientApiError ? e.message : "Failed to book appointment.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  if (booked) {
    return (
      <div style={card}>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8, color: "#0f766e" }}>Appointment Booked</div>
        <div style={{ fontSize: 13, marginBottom: 16 }}>
          Your reference number is <strong>{booked.appointment_number}</strong>.
        </div>
        <button style={primaryButton} onClick={() => router.push("/patient-portal/appointments")}>
          View My Appointments
        </button>
      </div>
    );
  }

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>Book an Appointment</h1>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
        Step {stepIndex + 1} of {STEPS.length}: {step}
      </div>

      {error && <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      <div style={card}>
        {step === "Branch" && (
          <div>
            {!branches && <div>Loading branches...</div>}
            {branches?.map((b) => (
              <div
                key={b.id}
                style={branchId === b.id ? optionRowSelected : optionRow}
                onClick={() => setBranchId(b.id)}
              >
                <div style={{ fontWeight: 600 }}>{b.name}</div>
                {b.address && <div style={{ fontSize: 12, color: "#64748b" }}>{b.address}</div>}
              </div>
            ))}
          </div>
        )}

        {step === "Department" && (
          <div>
            {!departments && <div>Loading departments...</div>}
            {departments?.map((d) => (
              <div
                key={d.id}
                style={departmentId === d.id ? optionRowSelected : optionRow}
                onClick={() => setDepartmentId(d.id)}
              >
                {d.name}
              </div>
            ))}
          </div>
        )}

        {step === "Doctor" && (
          <div>
            {!doctors && <div>Loading doctors...</div>}
            {doctors?.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No doctors available for this branch/department.</div>}
            {doctors?.map((d) => (
              <div
                key={d.id}
                style={doctorId === d.id ? optionRowSelected : optionRow}
                onClick={() => setDoctorId(d.id)}
              >
                <div style={{ fontWeight: 600 }}>Dr. {d.full_name}</div>
                {d.specialization && <div style={{ fontSize: 12, color: "#64748b" }}>{d.specialization}</div>}
              </div>
            ))}
          </div>
        )}

        {step === "Type" && (
          <div>
            {APPOINTMENT_TYPES.map((t) => (
              <div key={t} style={appointmentType === t ? optionRowSelected : optionRow} onClick={() => setAppointmentType(t)}>
                {t}
              </div>
            ))}
          </div>
        )}

        {step === "Date" && (
          <div>
            {!availableDates && <div>Loading available dates...</div>}
            {availableDates?.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No available dates in the next 45 days.</div>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {availableDates?.map((d) => (
                <div
                  key={d}
                  style={{ ...(date === d ? optionRowSelected : optionRow), marginBottom: 0, textAlign: "center", minWidth: 96 }}
                  onClick={() => setDate(d)}
                >
                  {d}
                </div>
              ))}
            </div>
          </div>
        )}

        {step === "Time" && (
          <div>
            {!slots && <div>Loading available times...</div>}
            {slots?.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No available time slots for this date.</div>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {slots?.map((s) => (
                <div
                  key={s.start_time}
                  style={{ ...(startTime === s.start_time ? optionRowSelected : optionRow), marginBottom: 0, textAlign: "center", minWidth: 90 }}
                  onClick={() => setStartTime(s.start_time)}
                >
                  {s.start_time.slice(0, 5)}
                </div>
              ))}
            </div>
          </div>
        )}

        {step === "Confirm" && (
          <div>
            <div style={{ fontSize: 13, lineHeight: 1.8 }}>
              <div><strong>Branch:</strong> {branches?.find((b) => b.id === branchId)?.name}</div>
              <div><strong>Department:</strong> {departments?.find((d) => d.id === departmentId)?.name ?? "Any"}</div>
              <div><strong>Doctor:</strong> Dr. {doctors?.find((d) => d.id === doctorId)?.full_name}</div>
              <div><strong>Type:</strong> {appointmentType}</div>
              <div><strong>Date:</strong> {date}</div>
              <div><strong>Time:</strong> {startTime?.slice(0, 5)}</div>
            </div>
            <textarea
              placeholder="Notes (optional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              style={{ width: "100%", marginTop: 12, padding: 8, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, minHeight: 60 }}
            />
          </div>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
        <button style={button} onClick={goBack} disabled={stepIndex === 0}>
          Back
        </button>
        {step !== "Confirm" ? (
          <button
            style={primaryButton}
            onClick={goNext}
            disabled={
              (step === "Branch" && !branchId) ||
              (step === "Doctor" && !doctorId) ||
              (step === "Type" && !appointmentType) ||
              (step === "Date" && !date) ||
              (step === "Time" && !startTime)
            }
          >
            Next
          </button>
        ) : (
          <button style={primaryButton} onClick={handleConfirm} disabled={submitting}>
            {submitting ? "Booking..." : "Confirm Booking"}
          </button>
        )}
      </div>
    </div>
  );
}
