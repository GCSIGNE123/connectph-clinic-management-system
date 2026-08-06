"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { patientLogin } from "@/features/patient-portal/api/client";

export default function PatientLoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await patientLogin(identifier, password);
      router.push("/patient-portal/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: 64, paddingLeft: 16, paddingRight: 16 }}>
      <form
        onSubmit={handleSubmit}
        style={{
          background: "#fff", border: "1px solid #ccfbf1", borderRadius: 12, padding: 32,
          width: "100%", maxWidth: 380, boxShadow: "0 4px 24px rgba(15,118,110,0.08)",
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4, color: "#0f172a" }}>Patient Portal Login</h1>
        <p style={{ fontSize: 12, color: "#64748b", marginBottom: 20 }}>
          Sign in with the email or mobile number on file with your clinic. Clinic staff should use the staff
          portal at /login.
        </p>

        <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>Email or mobile number</label>
        <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} style={inputStyle} required />

        <label style={{ display: "block", fontSize: 12, marginBottom: 4, marginTop: 12 }}>Password</label>
        <input
          type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          style={inputStyle} autoComplete="current-password" required
        />

        {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 12 }}>{error}</div>}

        <button type="submit" disabled={loading} style={buttonStyle}>
          {loading ? "Signing in..." : "Sign in"}
        </button>

        <div style={{ marginTop: 14, fontSize: 12, color: "#0f766e", textAlign: "center" }}>
          Forgot password? Contact your clinic&apos;s front desk to reset it.
        </div>
      </form>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 10px", borderRadius: 6, border: "1px solid #cbd5e1",
  boxSizing: "border-box", fontSize: 14,
};

const buttonStyle: React.CSSProperties = {
  width: "100%", marginTop: 20, padding: "10px 12px", borderRadius: 8, border: "none",
  background: "#0f766e", color: "#fff", fontWeight: 600, cursor: "pointer", fontSize: 14,
};
