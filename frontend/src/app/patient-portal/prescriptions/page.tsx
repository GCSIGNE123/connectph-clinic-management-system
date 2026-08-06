"use client";

import { useEffect, useState } from "react";
import { patientApiFetch } from "@/features/patient-portal/api/client";

interface Item {
  medicine: string; generic_name: string | null; brand_name: string | null; strength: string | null;
  dosage: string | null; frequency: string | null; duration: string | null; quantity: string | null; instructions: string | null;
}
interface Rx {
  id: string; prescription_number: string; status: string; created_at: string; doctor_name: string | null;
  is_current: boolean; items: Item[];
}

export default function PrescriptionsPage() {
  const [rows, setRows] = useState<Rx[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    patientApiFetch<Rx[]>("/patient-portal/prescriptions").then(setRows).catch((e) => setError(e.message));
  }, []);

  const current = rows?.filter((r) => r.is_current) ?? [];
  const past = rows?.filter((r) => !r.is_current) ?? [];

  function renderGroup(title: string, list: Rx[]) {
    return (
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>{title}</div>
        {list.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>None.</div>}
        {list.map((p) => (
          <div key={p.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, marginBottom: 8 }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>
              {p.prescription_number} - {new Date(p.created_at).toLocaleDateString()} - Dr. {p.doctor_name ?? "-"}
            </div>
            {p.items.map((i, idx) => (
              <div key={idx} style={{ fontSize: 12, color: "#475569", padding: "4px 0", borderTop: idx > 0 ? "1px solid #f1f5f9" : undefined }}>
                <strong>{i.medicine}</strong>{i.strength ? ` ${i.strength}` : ""} - {i.dosage ?? "-"} {i.frequency ?? ""} for {i.duration ?? "-"}
                {i.instructions ? <div style={{ color: "#94a3b8" }}>{i.instructions}</div> : null}
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Prescriptions</h1>
      {error && <div style={{ color: "#dc2626" }}>{error}</div>}
      {!rows && !error && <div>Loading...</div>}
      {rows && (
        <>
          {renderGroup("Current", current)}
          {renderGroup("Past", past)}
        </>
      )}
    </div>
  );
}
