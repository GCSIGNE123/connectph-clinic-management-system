import type { ReactNode } from "react";

/**
 * Platform Administration Portal shell - deliberately NOT the clinic
 * portal's (dashboard) route group layout. No shared Sidebar/TopNav, no
 * per-clinic branding. A distinct dark header identifies this as the
 * CONNECT.PH-internal portal so staff can never confuse it with a clinic's
 * own dashboard.
 */
export default function PlatformLayout({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", background: "#0b1220", color: "#e5e7eb" }}>
      <header
        style={{
          background: "#111827",
          borderBottom: "1px solid #1f2937",
          padding: "12px 24px",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: "linear-gradient(135deg,#7c3aed,#2563eb)",
          }}
        />
        <div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>CONNECT.PH Platform Administration</div>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>Internal SaaS operations portal - not a clinic account</div>
        </div>
      </header>
      <main style={{ padding: 24 }}>{children}</main>
    </div>
  );
}
