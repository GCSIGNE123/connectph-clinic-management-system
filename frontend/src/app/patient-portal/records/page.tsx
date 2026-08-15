"use client";

import { useEffect, useState } from "react";
import { patientApiFetch } from "@/features/patient-portal/api/client";
import { formatDate } from "@/lib/utils";

interface Diagnosis { id: string; diagnosis_type: string; status: string; notes: string | null; icd10_code: string | null; icd10_description: string | null; }
interface Attachment { id: string; attachment_type: string; file_name: string; file_url: string; }
interface Record_ { consultation_id: string; visit_date: string; doctor_name: string | null; diagnoses: Diagnosis[]; attachments: Attachment[]; }

export default function RecordsPage() {
  const [rows, setRows] = useState<Record_[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    patientApiFetch<Record_[]>("/patient-portal/medical-records").then(setRows).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>Medical Records</h1>
      <p style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
        Only records your clinician has explicitly shared with you are shown here.
      </p>
      {error && <div style={{ color: "#dc2626" }}>{error}</div>}
      {!rows && !error && <div>Loading...</div>}
      {rows && rows.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No shared records yet.</div>}
      {rows?.map((r) => (
        <div key={r.consultation_id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, marginBottom: 10 }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{formatDate(r.visit_date)} - Dr. {r.doctor_name ?? "-"}</div>
          {r.diagnoses.map((d) => (
            <div key={d.id} style={{ fontSize: 12, color: "#475569", marginTop: 6 }}>
              <strong>{d.diagnosis_type}</strong> ({d.status}) {d.icd10_code ? `[${d.icd10_code}]` : ""} {d.notes}
            </div>
          ))}
          {r.attachments.map((a) => (
            <div key={a.id} style={{ fontSize: 12, marginTop: 6 }}>
              <a href={a.file_url} target="_blank" rel="noreferrer" style={{ color: "#0f766e" }}>{a.file_name}</a> ({a.attachment_type})
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
