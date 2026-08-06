"use client";

import { useEffect, useState } from "react";
import {
  listTenants,
  suspendTenant,
  reactivateTenant,
  archiveTenant,
  type Tenant,
} from "@/features/platform-admin/api/tenants";

export default function TenantManagementPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function refresh() {
    try {
      const resp = await listTenants({ search: search || undefined });
      setTenants(resp.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tenants");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSuspend(t: Tenant) {
    const reason = window.prompt(`Reason for suspending ${t.name}?`, "Non-payment");
    if (reason === null) return;
    setBusyId(t.id);
    try {
      await suspendTenant(t.id, reason);
      await refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function handleReactivate(t: Tenant) {
    setBusyId(t.id);
    try {
      await reactivateTenant(t.id);
      await refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function handleArchive(t: Tenant) {
    if (!window.confirm(`Archive ${t.name}? This is a soft, reversible-in-DB lifecycle state.`)) return;
    setBusyId(t.id);
    try {
      await archiveTenant(t.id);
      await refresh();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 16 }}>Tenant Management</h1>

      <div style={{ marginBottom: 16 }}>
        <input
          placeholder="Search by name, slug, or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && refresh()}
          style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid #374151", background: "#0b1220", color: "#e5e7eb", width: 320 }}
        />
        <button onClick={refresh} style={{ marginLeft: 8 }}>
          Search
        </button>
      </div>

      {error && <div style={{ color: "#f87171" }}>{error}</div>}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #1f2937" }}>
            <th style={th}>Name</th>
            <th style={th}>Slug</th>
            <th style={th}>Email</th>
            <th style={th}>Status</th>
            <th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((t) => (
            <tr key={t.id} style={{ borderBottom: "1px solid #1f2937" }}>
              <td style={td}>{t.name}</td>
              <td style={td}>{t.slug}</td>
              <td style={td}>{t.email ?? "-"}</td>
              <td style={td}>
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: 999,
                    fontSize: 11,
                    background:
                      t.status === "Active" ? "#065f46" : t.status === "Suspended" ? "#7f1d1d" : "#374151",
                  }}
                >
                  {t.status}
                </span>
              </td>
              <td style={td}>
                {t.status === "Active" && (
                  <button disabled={busyId === t.id} onClick={() => handleSuspend(t)}>
                    Suspend
                  </button>
                )}
                {t.status === "Suspended" && (
                  <button disabled={busyId === t.id} onClick={() => handleReactivate(t)}>
                    Reactivate
                  </button>
                )}
                {t.status !== "Archived" && (
                  <button disabled={busyId === t.id} onClick={() => handleArchive(t)} style={{ marginLeft: 8 }}>
                    Archive
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 6px", fontSize: 12, color: "#9ca3af" };
const td: React.CSSProperties = { padding: "8px 6px", fontSize: 13 };
