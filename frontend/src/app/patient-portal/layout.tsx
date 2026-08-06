"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { patientLogout } from "@/features/patient-portal/api/client";

/**
 * Patient Portal shell - deliberately NOT the clinic staff (dashboard)
 * layout and NOT the Platform Administration Portal layout. A distinct
 * teal header identifies this as the patient-facing portal.
 */
const NAV = [
  { href: "/patient-portal/dashboard", label: "Dashboard" },
  { href: "/patient-portal/appointments", label: "Appointments" },
  { href: "/patient-portal/laboratory", label: "Laboratory" },
  { href: "/patient-portal/prescriptions", label: "Prescriptions" },
  { href: "/patient-portal/records", label: "Medical Records" },
  { href: "/patient-portal/billing", label: "Billing" },
  { href: "/patient-portal/notifications", label: "Notifications" },
  { href: "/patient-portal/profile", label: "Profile" },
];

export default function PatientPortalLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === "/patient-portal/login";

  if (isLogin) {
    return <div style={{ minHeight: "100vh", background: "#f0fdfa" }}>{children}</div>;
  }

  function handleLogout() {
    patientLogout();
    router.push("/patient-portal/login");
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc", color: "#0f172a" }}>
      <header
        style={{
          background: "#0f766e",
          color: "#fff",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          <div style={{ width: 26, height: 26, borderRadius: 6, background: "#fff", flexShrink: 0 }} />
          <div style={{ fontWeight: 700, fontSize: 14, whiteSpace: "nowrap" }}>CONNECT.PH Patient Portal</div>
        </div>
        <button
          onClick={handleLogout}
          style={{
            background: "transparent", border: "1px solid rgba(255,255,255,0.5)", color: "#fff",
            borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer",
          }}
        >
          Sign out
        </button>
      </header>
      <nav
        style={{
          background: "#fff", borderBottom: "1px solid #e2e8f0", padding: "0 8px",
          display: "flex", gap: 4, overflowX: "auto", WebkitOverflowScrolling: "touch",
        }}
      >
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            style={{
              padding: "10px 12px", fontSize: 13, whiteSpace: "nowrap", textDecoration: "none",
              color: pathname?.startsWith(item.href) ? "#0f766e" : "#475569",
              borderBottom: pathname?.startsWith(item.href) ? "2px solid #0f766e" : "2px solid transparent",
              fontWeight: pathname?.startsWith(item.href) ? 600 : 400,
            }}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <main style={{ padding: 16, maxWidth: 960, margin: "0 auto", width: "100%", boxSizing: "border-box" }}>
        {children}
      </main>
    </div>
  );
}
