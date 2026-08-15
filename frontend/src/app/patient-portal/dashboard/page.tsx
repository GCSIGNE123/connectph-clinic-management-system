"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { patientApiFetch } from "@/features/patient-portal/api/client";
import { formatDate, formatDateTime } from "@/lib/utils";

interface Dashboard {
  upcoming_appointments: { id: string; appointment_number: string; appointment_date: string; start_time: string; status: string; doctor_name: string | null }[];
  recent_visits: { id: string; visit_number: string; visit_date: string; status: string }[];
  outstanding_balance: string;
  latest_lab_results: { id: string; test_type: string; released_at: string | null }[];
  recent_prescriptions: { id: string; prescription_number: string; created_at: string; item_count: number }[];
  announcements: string[];
}

const card: React.CSSProperties = {
  background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, marginBottom: 16,
};
const heading: React.CSSProperties = { fontSize: 14, fontWeight: 700, marginBottom: 10, color: "#0f172a" };

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    patientApiFetch<Dashboard>("/patient-portal/dashboard").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div style={{ color: "#dc2626" }}>{error}</div>;
  if (!data) return <div>Loading...</div>;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>My Dashboard</h1>
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

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginBottom: 4 }}>
        <div style={{ ...card, background: "#0f766e", color: "#fff" }}>
          <div style={{ fontSize: 12, opacity: 0.85 }}>Outstanding Balance</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>PHP {Number(data.outstanding_balance).toFixed(2)}</div>
        </div>
      </div>

      <div style={card}>
        <div style={heading}>Upcoming Appointments</div>
        {data.upcoming_appointments.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No upcoming appointments.</div>}
        {data.upcoming_appointments.map((a) => (
          <div key={a.id} style={{ fontSize: 13, padding: "6px 0", borderBottom: "1px solid #f1f5f9" }}>
            {formatDate(a.appointment_date)} {a.start_time} - Dr. {a.doctor_name ?? "TBD"} ({a.status})
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={heading}>Recent Visits</div>
        {data.recent_visits.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No visit history yet.</div>}
        {data.recent_visits.map((v) => (
          <div key={v.id} style={{ fontSize: 13, padding: "6px 0", borderBottom: "1px solid #f1f5f9" }}>
            {formatDate(v.visit_date)} - {v.visit_number} ({v.status})
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={heading}>Latest Released Lab Results</div>
        {data.latest_lab_results.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No released lab results yet.</div>}
        {data.latest_lab_results.map((l) => (
          <div key={l.id} style={{ fontSize: 13, padding: "6px 0", borderBottom: "1px solid #f1f5f9" }}>
            {l.test_type} - released {l.released_at ? formatDateTime(l.released_at) : "-"}
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={heading}>Recent Prescriptions</div>
        {data.recent_prescriptions.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No prescriptions yet.</div>}
        {data.recent_prescriptions.map((p) => (
          <div key={p.id} style={{ fontSize: 13, padding: "6px 0", borderBottom: "1px solid #f1f5f9" }}>
            {p.prescription_number} - {p.item_count} item(s)
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={heading}>Clinic Announcements</div>
        {data.announcements.map((a, i) => (
          <div key={i} style={{ fontSize: 13, color: "#64748b" }}>{a}</div>
        ))}
      </div>
    </div>
  );
}
