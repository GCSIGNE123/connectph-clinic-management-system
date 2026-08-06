"use client";

import { useEffect, useState } from "react";
import { patientApiFetch } from "@/features/patient-portal/api/client";

interface Profile {
  id: string; first_name: string; middle_name: string | null; last_name: string; mobile_number: string;
  telephone_number: string | null; email: string | null; address_line: string | null; barangay: string | null;
  city: string | null; province: string | null; zip_code: string | null; photo_url: string | null;
  emergency_contact_name: string | null; emergency_contact_phone: string | null; is_email_verified: boolean;
  last_login_at: string | null;
}
interface Prefs {
  appointment_reminders: boolean; lab_result_alerts: boolean; billing_notices: boolean; clinic_announcements: boolean; preferred_channel: string;
}

const input: React.CSSProperties = { width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13, boxSizing: "border-box" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, marginBottom: 16 };
const label: React.CSSProperties = { fontSize: 12, color: "#475569", display: "block", marginBottom: 3, marginTop: 8 };

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");

  useEffect(() => {
    patientApiFetch<Profile>("/patient-portal/profile").then(setProfile);
    patientApiFetch<Prefs>("/patient-portal/notification-preferences").then(setPrefs);
  }, []);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    const updated = await patientApiFetch<Profile>("/patient-portal/profile", {
      method: "PUT",
      body: {
        mobile_number: profile.mobile_number, telephone_number: profile.telephone_number, email: profile.email,
        address_line: profile.address_line, barangay: profile.barangay, city: profile.city, province: profile.province,
        zip_code: profile.zip_code, emergency_contact_name: profile.emergency_contact_name,
        emergency_contact_phone: profile.emergency_contact_phone,
      },
    });
    setProfile(updated);
    setMsg("Profile updated.");
  }

  async function uploadPhoto() {
    const res = await patientApiFetch<{ public_url: string }>("/patient-portal/profile/photo", { method: "POST" });
    setProfile((p) => (p ? { ...p, photo_url: res.public_url } : p));
    setMsg("Photo updated (stub upload - no real file storage wired yet).");
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    try {
      await patientApiFetch("/patient-portal/auth/change-password", { method: "POST", body: { old_password: oldPw, new_password: newPw } });
      setMsg("Password changed.");
      setOldPw(""); setNewPw("");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Failed to change password");
    }
  }

  async function savePrefs(key: keyof Prefs, value: boolean) {
    const updated = await patientApiFetch<Prefs>("/patient-portal/notification-preferences", { method: "PUT", body: { [key]: value } });
    setPrefs(updated);
  }

  if (!profile || !prefs) return <div>Loading...</div>;

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>My Profile</h1>
      {msg && <div style={{ fontSize: 12, color: "#0f766e", marginBottom: 12 }}>{msg}</div>}

      <div style={card}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ width: 64, height: 64, borderRadius: "50%", background: "#ccfbf1", overflow: "hidden", flexShrink: 0 }}>
            {profile.photo_url && <img src={profile.photo_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
          </div>
          <button onClick={uploadPhoto} style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer", fontSize: 12 }}>
            Upload photo
          </button>
        </div>

        <form onSubmit={saveProfile}>
          <label style={label}>Mobile Number</label>
          <input style={input} value={profile.mobile_number} onChange={(e) => setProfile({ ...profile, mobile_number: e.target.value })} />
          <label style={label}>Email</label>
          <input style={input} value={profile.email ?? ""} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
          <label style={label}>Address</label>
          <input style={input} value={profile.address_line ?? ""} onChange={(e) => setProfile({ ...profile, address_line: e.target.value })} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
            <div><label style={label}>City</label><input style={input} value={profile.city ?? ""} onChange={(e) => setProfile({ ...profile, city: e.target.value })} /></div>
            <div><label style={label}>Province</label><input style={input} value={profile.province ?? ""} onChange={(e) => setProfile({ ...profile, province: e.target.value })} /></div>
            <div><label style={label}>Zip</label><input style={input} value={profile.zip_code ?? ""} onChange={(e) => setProfile({ ...profile, zip_code: e.target.value })} /></div>
          </div>
          <label style={label}>Emergency Contact Name</label>
          <input style={input} value={profile.emergency_contact_name ?? ""} onChange={(e) => setProfile({ ...profile, emergency_contact_name: e.target.value })} />
          <label style={label}>Emergency Contact Phone</label>
          <input style={input} value={profile.emergency_contact_phone ?? ""} onChange={(e) => setProfile({ ...profile, emergency_contact_phone: e.target.value })} />
          <button type="submit" style={{ marginTop: 12, padding: "8px 16px", borderRadius: 6, border: "none", background: "#0f766e", color: "#fff", cursor: "pointer", fontSize: 13 }}>
            Save Profile
          </button>
        </form>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>Change Password</div>
        <form onSubmit={changePassword}>
          <label style={label}>Current Password</label>
          <input type="password" style={input} value={oldPw} onChange={(e) => setOldPw(e.target.value)} required />
          <label style={label}>New Password</label>
          <input type="password" style={input} value={newPw} onChange={(e) => setNewPw(e.target.value)} required />
          <button type="submit" style={{ marginTop: 12, padding: "8px 16px", borderRadius: 6, border: "none", background: "#0f766e", color: "#fff", cursor: "pointer", fontSize: 13 }}>
            Change Password
          </button>
        </form>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>Notification Preferences</div>
        {([
          ["appointment_reminders", "Appointment reminders"],
          ["lab_result_alerts", "Lab result alerts"],
          ["billing_notices", "Billing notices"],
          ["clinic_announcements", "Clinic announcements"],
        ] as const).map(([key, text]) => (
          <label key={key} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "6px 0" }}>
            <input type="checkbox" checked={prefs[key]} onChange={(e) => savePrefs(key, e.target.checked)} />
            {text}
          </label>
        ))}
        <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 6 }}>
          In-app delivery only for now - email/SMS/push delivery is not wired up yet.
        </div>
      </div>
    </div>
  );
}
