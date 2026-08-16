"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  listTenantUsers,
  listRoles,
  createTenantUser,
  updateTenantUser,
  deleteTenantUser,
  resetTenantUserPassword,
  lockTenantUser,
  unlockTenantUser,
  forceLogoutTenantUser,
  type TenantUser,
  type Role,
} from "@/features/platform-admin/api/tenant-users";
import { PlatformApiError } from "@/features/platform-admin/api/client";

const emptyForm = {
  firstName: "",
  lastName: "",
  email: "",
  username: "",
  password: "",
  roleId: "",
};

const emptyEditForm = {
  firstName: "",
  lastName: "",
  email: "",
  username: "",
  roleId: "",
};

export default function TenantUsersPage() {
  const params = useParams<{ clinicId: string }>();
  const clinicId = params.clinicId;

  const [users, setUsers] = useState<TenantUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [editingUser, setEditingUser] = useState<TenantUser | null>(null);
  const [editForm, setEditForm] = useState(emptyEditForm);
  const [editError, setEditError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [resetTarget, setResetTarget] = useState<TenantUser | null>(null);
  const [resetPasswordValue, setResetPasswordValue] = useState("");
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [resetDone, setResetDone] = useState(false);

  async function refresh() {
    try {
      setUsers(await listTenantUsers(clinicId));
    } catch (e) {
      setError(e instanceof PlatformApiError ? e.message : "Failed to load tenant users");
    }
  }

  useEffect(() => {
    refresh();
    listRoles()
      .then((r) => {
        setRoles(r);
        setForm((prev) => (prev.roleId ? prev : { ...prev, roleId: r[0]?.id ?? "" }));
      })
      .catch(() => setError("Failed to load roles"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      await createTenantUser(clinicId, form);
      setForm({ ...emptyForm, roleId: roles[0]?.id ?? "" });
      setShowCreateForm(false);
      await refresh();
    } catch (err) {
      setCreateError(err instanceof PlatformApiError ? err.message : "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  function openEdit(u: TenantUser) {
    setShowCreateForm(false);
    setEditingUser(u);
    setEditError(null);
    const role = roles.find((r) => r.name === u.role);
    setEditForm({
      firstName: u.first_name,
      lastName: u.last_name,
      email: u.email,
      username: u.username,
      roleId: role?.id ?? "",
    });
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingUser) return;
    setEditError(null);
    setSaving(true);
    try {
      await updateTenantUser(clinicId, editingUser.id, editForm);
      setEditingUser(null);
      await refresh();
    } catch (err) {
      setEditError(err instanceof PlatformApiError ? err.message : "Failed to update user");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(u: TenantUser) {
    if (
      !window.confirm(
        `Permanently delete ${u.first_name} ${u.last_name} (${u.email})? This cannot be undone from this screen.`
      )
    ) {
      return;
    }
    setBusyId(u.id);
    try {
      await deleteTenantUser(clinicId, u.id);
      await refresh();
    } catch (err) {
      window.alert(err instanceof PlatformApiError ? err.message : "Failed to delete user");
    } finally {
      setBusyId(null);
    }
  }

  function openResetPassword(u: TenantUser) {
    setShowCreateForm(false);
    setEditingUser(null);
    setResetTarget(u);
    setResetPasswordValue("");
    setResetError(null);
    setResetDone(false);
  }

  function closeResetPassword() {
    setResetTarget(null);
    setResetPasswordValue("");
    setResetError(null);
    setResetDone(false);
  }

  async function handleSubmitResetPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!resetTarget) return;
    if (resetPasswordValue.length < 8) {
      setResetError("Password must be at least 8 characters.");
      return;
    }
    setResetError(null);
    setResetSubmitting(true);
    try {
      await resetTenantUserPassword(clinicId, resetTarget.id, resetPasswordValue);
      setResetDone(true);
      setResetPasswordValue("");
    } catch (err) {
      setResetError(err instanceof PlatformApiError ? err.message : "Failed to reset password");
    } finally {
      setResetSubmitting(false);
    }
  }

  async function handleLock(u: TenantUser) {
    setBusyId(u.id);
    try {
      await lockTenantUser(clinicId, u.id);
      await refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function handleUnlock(u: TenantUser) {
    setBusyId(u.id);
    try {
      await unlockTenantUser(clinicId, u.id);
      await refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function handleForceLogout(u: TenantUser) {
    if (!window.confirm(`Force-logout ${u.email}? This revokes all of their active sessions immediately.`)) return;
    setBusyId(u.id);
    try {
      await forceLogoutTenantUser(clinicId, u.id);
      window.alert("All active sessions revoked.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <Link href="/platform/tenants" style={{ fontSize: 12, color: "#9ca3af" }}>
        &larr; Back to Tenant Management
      </Link>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8, marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Clinic Users</h1>
        <button
          onClick={() => {
            setShowCreateForm((v) => !v);
            setCreateError(null);
          }}
          style={{
            padding: "8px 14px",
            borderRadius: 6,
            border: "none",
            background: "linear-gradient(135deg,#7c3aed,#2563eb)",
            color: "white",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {showCreateForm ? "Cancel" : "+ New User"}
        </button>
      </div>

      {showCreateForm && (
        <form
          onSubmit={handleCreate}
          style={{
            background: "#111827",
            border: "1px solid #1f2937",
            borderRadius: 12,
            padding: 24,
            marginBottom: 24,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
          }}
        >
          <FormField label="First name" value={form.firstName} onChange={(v) => setForm({ ...form, firstName: v })} required />
          <FormField label="Last name" value={form.lastName} onChange={(v) => setForm({ ...form, lastName: v })} required />
          <FormField label="Email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} type="email" required />
          <FormField label="Username" value={form.username} onChange={(v) => setForm({ ...form, username: v })} required />
          <FormField label="Password" value={form.password} onChange={(v) => setForm({ ...form, password: v })} type="password" required />

          <label style={{ display: "block", fontSize: 12, color: "#9ca3af" }}>
            Role
            <select
              value={form.roleId}
              onChange={(e) => setForm({ ...form, roleId: e.target.value })}
              required
              style={{
                display: "block",
                width: "100%",
                marginTop: 4,
                padding: "8px 10px",
                borderRadius: 6,
                border: "1px solid #374151",
                background: "#0b1220",
                color: "#e5e7eb",
              }}
            >
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>

          {createError && <div style={{ gridColumn: "1 / -1", color: "#f87171", fontSize: 12 }}>{createError}</div>}

          <div style={{ gridColumn: "1 / -1", marginTop: 8 }}>
            <button
              type="submit"
              disabled={creating}
              style={{
                padding: "8px 16px",
                borderRadius: 6,
                border: "none",
                background: "linear-gradient(135deg,#7c3aed,#2563eb)",
                color: "white",
                fontWeight: 600,
                cursor: creating ? "default" : "pointer",
                opacity: creating ? 0.6 : 1,
              }}
            >
              {creating ? "Creating..." : "Create user"}
            </button>
          </div>
        </form>
      )}

      {editingUser && (
        <form
          onSubmit={handleSaveEdit}
          style={{
            background: "#111827",
            border: "1px solid #1f2937",
            borderRadius: 12,
            padding: 24,
            marginBottom: 24,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
          }}
        >
          <div style={{ gridColumn: "1 / -1", fontSize: 13, color: "#9ca3af" }}>
            Editing {editingUser.first_name} {editingUser.last_name}
          </div>
          <FormField label="First name" value={editForm.firstName} onChange={(v) => setEditForm({ ...editForm, firstName: v })} required />
          <FormField label="Last name" value={editForm.lastName} onChange={(v) => setEditForm({ ...editForm, lastName: v })} required />
          <FormField label="Email" value={editForm.email} onChange={(v) => setEditForm({ ...editForm, email: v })} type="email" required />
          <FormField label="Username" value={editForm.username} onChange={(v) => setEditForm({ ...editForm, username: v })} required />

          <label style={{ display: "block", fontSize: 12, color: "#9ca3af" }}>
            Role
            <select
              value={editForm.roleId}
              onChange={(e) => setEditForm({ ...editForm, roleId: e.target.value })}
              required
              style={{
                display: "block",
                width: "100%",
                marginTop: 4,
                padding: "8px 10px",
                borderRadius: 6,
                border: "1px solid #374151",
                background: "#0b1220",
                color: "#e5e7eb",
              }}
            >
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>

          {editError && <div style={{ gridColumn: "1 / -1", color: "#f87171", fontSize: 12 }}>{editError}</div>}

          <div style={{ gridColumn: "1 / -1", marginTop: 8, display: "flex", gap: 8 }}>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: "8px 16px",
                borderRadius: 6,
                border: "none",
                background: "linear-gradient(135deg,#7c3aed,#2563eb)",
                color: "white",
                fontWeight: 600,
                cursor: saving ? "default" : "pointer",
                opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? "Saving..." : "Save changes"}
            </button>
            <button
              type="button"
              onClick={() => setEditingUser(null)}
              style={{
                padding: "8px 16px",
                borderRadius: 6,
                border: "1px solid #374151",
                background: "transparent",
                color: "#e5e7eb",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {resetTarget && (
        <div
          style={{
            background: "#111827",
            border: "1px solid #1f2937",
            borderRadius: 12,
            padding: 24,
            marginBottom: 24,
          }}
        >
          <div style={{ fontSize: 13, color: "#9ca3af", marginBottom: 12 }}>
            Reset password for {resetTarget.first_name} {resetTarget.last_name} ({resetTarget.email})
          </div>

          {resetDone ? (
            <div>
              <p style={{ color: "#34d399", fontSize: 13, marginBottom: 12 }}>
                Password reset. All of this user&apos;s active sessions have been revoked.
              </p>
              <button
                type="button"
                onClick={closeResetPassword}
                style={{
                  padding: "8px 16px",
                  borderRadius: 6,
                  border: "1px solid #374151",
                  background: "transparent",
                  color: "#e5e7eb",
                  cursor: "pointer",
                }}
              >
                Close
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmitResetPassword}>
              <FormField
                label="New password (min 8 characters)"
                value={resetPasswordValue}
                onChange={setResetPasswordValue}
                type="password"
                required
              />

              {resetError && <div style={{ color: "#f87171", fontSize: 12, marginTop: 8 }}>{resetError}</div>}

              <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                <button
                  type="submit"
                  disabled={resetSubmitting}
                  style={{
                    padding: "8px 16px",
                    borderRadius: 6,
                    border: "none",
                    background: "linear-gradient(135deg,#7c3aed,#2563eb)",
                    color: "white",
                    fontWeight: 600,
                    cursor: resetSubmitting ? "default" : "pointer",
                    opacity: resetSubmitting ? 0.6 : 1,
                  }}
                >
                  {resetSubmitting ? "Resetting..." : "Reset password"}
                </button>
                <button
                  type="button"
                  onClick={closeResetPassword}
                  style={{
                    padding: "8px 16px",
                    borderRadius: 6,
                    border: "1px solid #374151",
                    background: "transparent",
                    color: "#e5e7eb",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {error && <div style={{ color: "#f87171" }}>{error}</div>}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #1f2937" }}>
            <th style={th}>Name</th>
            <th style={th}>Email</th>
            <th style={th}>Username</th>
            <th style={th}>Role</th>
            <th style={th}>Status</th>
            <th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderBottom: "1px solid #1f2937" }}>
              <td style={td}>
                {u.first_name} {u.last_name}
              </td>
              <td style={td}>{u.email}</td>
              <td style={td}>{u.username}</td>
              <td style={td}>{u.role ?? "-"}</td>
              <td style={td}>
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: 999,
                    fontSize: 11,
                    background: u.status === "Locked" ? "#7f1d1d" : u.status === "Active" ? "#065f46" : "#374151",
                  }}
                >
                  {u.status}
                </span>
              </td>
              <td style={td}>
                <button disabled={busyId === u.id} onClick={() => openEdit(u)}>
                  Edit
                </button>
                <button disabled={busyId === u.id} onClick={() => openResetPassword(u)} style={{ marginLeft: 8 }}>
                  Reset password
                </button>
                {u.status === "Locked" ? (
                  <button disabled={busyId === u.id} onClick={() => handleUnlock(u)} style={{ marginLeft: 8 }}>
                    Unlock
                  </button>
                ) : (
                  <button disabled={busyId === u.id} onClick={() => handleLock(u)} style={{ marginLeft: 8 }}>
                    Lock
                  </button>
                )}
                <button disabled={busyId === u.id} onClick={() => handleForceLogout(u)} style={{ marginLeft: 8 }}>
                  Force logout
                </button>
                <button
                  disabled={busyId === u.id}
                  onClick={() => handleDelete(u)}
                  style={{ marginLeft: 8, color: "#f87171" }}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {users.length === 0 && !error && <p style={{ color: "#9ca3af", marginTop: 16 }}>No users yet.</p>}
    </div>
  );
}

function FormField({
  label,
  value,
  onChange,
  type = "text",
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
}) {
  return (
    <label style={{ display: "block", fontSize: 12, color: "#9ca3af" }}>
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        style={{
          display: "block",
          width: "100%",
          marginTop: 4,
          padding: "8px 10px",
          borderRadius: 6,
          border: "1px solid #374151",
          background: "#0b1220",
          color: "#e5e7eb",
        }}
      />
    </label>
  );
}

const th: React.CSSProperties = { padding: "8px 6px", fontSize: 12, color: "#9ca3af" };
const td: React.CSSProperties = { padding: "8px 6px", fontSize: 13 };
