"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { platformLogin } from "@/features/platform-admin/api/client";

export default function PlatformLoginPage() {
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
      await platformLogin(identifier, password);
      router.push("/platform/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: 80 }}>
      <form
        onSubmit={handleSubmit}
        style={{
          background: "#111827",
          border: "1px solid #1f2937",
          borderRadius: 12,
          padding: 32,
          width: 360,
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>Platform Administrator Login</h1>
        <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 20 }}>
          For CONNECT.PH staff only. Clinic staff should use the clinic portal at /login.
        </p>

        <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>Email or username</label>
        <input
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          style={inputStyle}
          autoComplete="username"
          required
        />

        <label style={{ display: "block", fontSize: 12, marginBottom: 4, marginTop: 12 }}>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={inputStyle}
          autoComplete="current-password"
          required
        />

        {error && (
          <div style={{ color: "#f87171", fontSize: 12, marginTop: 12 }}>{error}</div>
        )}

        <button type="submit" disabled={loading} style={buttonStyle}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid #374151",
  background: "#0b1220",
  color: "#e5e7eb",
};

const buttonStyle: React.CSSProperties = {
  width: "100%",
  marginTop: 20,
  padding: "10px 0",
  borderRadius: 6,
  border: "none",
  background: "linear-gradient(135deg,#7c3aed,#2563eb)",
  color: "white",
  fontWeight: 600,
  cursor: "pointer",
};
