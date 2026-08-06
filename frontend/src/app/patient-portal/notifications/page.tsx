"use client";

import { useEffect, useState } from "react";
import { patientApiFetch } from "@/features/patient-portal/api/client";

interface Notif { id: string; notification_type: string; title: string; body: string | null; is_read: boolean; created_at: string; }

export default function NotificationsPage() {
  const [rows, setRows] = useState<Notif[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    patientApiFetch<Notif[]>("/patient-portal/notifications").then(setRows).catch((e) => setError(e.message));
  }, []);

  async function markRead(id: string) {
    const updated = await patientApiFetch<Notif>(`/patient-portal/notifications/${id}/read`, { method: "POST" });
    setRows((prev) => prev?.map((n) => (n.id === id ? updated : n)) ?? null);
  }

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Notifications</h1>
      {error && <div style={{ color: "#dc2626" }}>{error}</div>}
      {!rows && !error && <div>Loading...</div>}
      {rows && rows.length === 0 && <div style={{ fontSize: 13, color: "#64748b" }}>No notifications yet.</div>}
      {rows?.map((n) => (
        <div
          key={n.id}
          onClick={() => !n.is_read && markRead(n.id)}
          style={{
            background: n.is_read ? "#fff" : "#f0fdfa", border: "1px solid #e2e8f0", borderRadius: 10,
            padding: 12, marginBottom: 8, cursor: n.is_read ? "default" : "pointer",
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 13 }}>{n.title} {!n.is_read && <span style={{ color: "#0f766e", fontSize: 11 }}>NEW</span>}</div>
          {n.body && <div style={{ fontSize: 12, color: "#475569" }}>{n.body}</div>}
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>{n.notification_type} - {new Date(n.created_at).toLocaleString()}</div>
        </div>
      ))}
    </div>
  );
}
