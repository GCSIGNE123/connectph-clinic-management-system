"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSystemHealth, type SystemHealth } from "@/features/platform-admin/api/tenants";
import { platformLogout } from "@/features/platform-admin/api/client";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

export default function PlatformDashboardPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystemHealth().then(setHealth).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>System Health</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <Link href="/platform/tenants" style={{ color: "#93c5fd" }}>
            Tenant Management
          </Link>
          <button onClick={() => platformLogout().then(() => (window.location.href = "/platform/login"))}>
            Logout
          </button>
        </div>
      </div>

      {error && <div style={{ color: "#f87171" }}>{error}</div>}

      {health && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 16 }}>
          <StatCard label="Total Clinics" value={health.total_clinics} />
          <StatCard label="Active Clinics" value={health.active_clinics} />
          <StatCard label="Suspended Clinics" value={health.suspended_clinics} />
          <StatCard label="Trial Subscriptions" value={health.trial_subscriptions} />
          <StatCard label="Expired Subscriptions" value={health.expired_subscriptions} />
          <StatCard label="Online Users" value={health.online_users} />
          <StatCard label="Database Size" value={formatBytes(health.database_size_bytes)} />
          <StatCard label="Background Jobs" value={health.background_jobs_total} />
          <StatCard label="Failed Jobs" value={health.background_jobs_failed} />
          <StatCard label="API Requests Today" value={health.api_requests_today ?? "N/A (not tracked yet)"} />
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 10, padding: 16 }}>
      <div style={{ fontSize: 12, color: "#9ca3af" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{value}</div>
    </div>
  );
}
