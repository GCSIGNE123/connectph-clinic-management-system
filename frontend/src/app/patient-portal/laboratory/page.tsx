"use client";

import { useEffect, useState } from "react";
import { patientApiFetch } from "@/features/patient-portal/api/client";

interface LabParam {
  parameter_name: string; result_type: string; numeric_value: string | null; text_value: string | null;
  normal_range: string | null; units: string | null; interpretation: string | null;
}
interface LabOrder {
  id: string; test_type: string; status: string; released_at: string | null; results: LabParam[]; pdf_available: boolean;
}

export default function LaboratoryPage() {
  const [rows, setRows] = useState<LabOrder[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    patientApiFetch<LabOrder[]>("/patient-portal/laboratory").then(setRows).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>Laboratory Results</h1>
      <p style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
        Only released results are shown. Results still being processed are not visible here.
      </p>
      {error && <div style={{ color: "#dc2626" }}>{error}</div>}
      {!rows && !error && <div>Loading...</div>}
      {rows && rows.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No released lab results yet.</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {rows?.map((o) => (
          <div key={o.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{o.test_type}</div>
            <div style={{ fontSize: 12, color: "#0f766e", marginBottom: 8 }}>Released {o.released_at ?? "-"}</div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#64748b" }}>
                    <th style={{ padding: 4 }}>Parameter</th>
                    <th style={{ padding: 4 }}>Result</th>
                    <th style={{ padding: 4 }}>Range</th>
                    <th style={{ padding: 4 }}>Units</th>
                    <th style={{ padding: 4 }}>Interp.</th>
                  </tr>
                </thead>
                <tbody>
                  {o.results.map((r, i) => (
                    <tr key={i} style={{ borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: 4 }}>{r.parameter_name}</td>
                      <td style={{ padding: 4 }}>{r.numeric_value ?? r.text_value ?? "-"}</td>
                      <td style={{ padding: 4 }}>{r.normal_range ?? "-"}</td>
                      <td style={{ padding: 4 }}>{r.units ?? "-"}</td>
                      <td style={{ padding: 4 }}>{r.interpretation ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 8 }}>No PDF available for this result yet.</div>
          </div>
        ))}
      </div>
    </div>
  );
}
