"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  listTenants,
  suspendTenant,
  reactivateTenant,
  archiveTenant,
  createTenant,
  updateTenant,
  deleteTenant,
  type Tenant,
} from "@/features/platform-admin/api/tenants";
import { PlatformApiError } from "@/features/platform-admin/api/client";

const emptyForm = {
  name: "",
  slug: "",
  email: "",
  ownerFirstName: "",
  ownerLastName: "",
  ownerEmail: "",
  ownerUsername: "",
  ownerPassword: "",
};

const emptyEditForm = { name: "", slug: "", email: "" };

export default function TenantManagementPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null);
  const [editForm, setEditForm] = useState(emptyEditForm);
  const [editError, setEditError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function slugify(value: string): string {
    return value
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "");
  }

  function updateField(field: keyof typeof emptyForm, value: string) {
    setForm((prev) => {
      const next = { ...prev, [field]: value };
      // Auto-derive the slug from the clinic name until the operator edits
      // slug directly, mirroring the common "name -> URL slug" pattern.
      if (field === "name" && (prev.slug === "" || prev.slug === slugify(prev.name))) {
        next.slug = slugify(value);
      }
      return next;
    });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      await createTenant({
        name: form.name,
        slug: form.slug,
        email: form.email || undefined,
        ownerFirstName: form.ownerFirstName,
        ownerLastName: form.ownerLastName,
        ownerEmail: form.ownerEmail,
        ownerUsername: form.ownerUsername,
        ownerPassword: form.ownerPassword,
      });
      setForm(emptyForm);
      setShowCreateForm(false);
      await refresh();
    } catch (err) {
      setCreateError(err instanceof PlatformApiError ? err.message : "Failed to create tenant");
    } finally {
      setCreating(false);
    }
  }

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

  function openEdit(t: Tenant) {
    setShowCreateForm(false);
    setEditingTenant(t);
    setEditError(null);
    setEditForm({ name: t.name, slug: t.slug, email: t.email ?? "" });
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingTenant) return;
    setEditError(null);
    setSaving(true);
    try {
      await updateTenant(editingTenant.id, {
        name: editForm.name,
        slug: editForm.slug,
        email: editForm.email || undefined,
      });
      setEditingTenant(null);
      await refresh();
    } catch (err) {
      setEditError(err instanceof PlatformApiError ? err.message : "Failed to update tenant");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(t: Tenant) {
    if (t.status !== "Archived") {
      window.alert(`${t.name} must be archived before it can be deleted.`);
      return;
    }
    if (
      !window.confirm(
        `Permanently delete ${t.name}? This cannot be undone from this screen. All of this clinic's data (patients, visits, billing, etc.) stays in the database but this tenant will disappear from every list.`
      )
    ) {
      return;
    }
    setBusyId(t.id);
    try {
      await deleteTenant(t.id);
      await refresh();
    } catch (err) {
      window.alert(err instanceof PlatformApiError ? err.message : "Failed to delete tenant");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Tenant Management</h1>
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
          {showCreateForm ? "Cancel" : "+ New Tenant"}
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
          <div style={{ gridColumn: "1 / -1", fontSize: 13, fontWeight: 600, color: "#e5e7eb" }}>Clinic</div>
          <FormField label="Clinic name" value={form.name} onChange={(v) => updateField("name", v)} required />
          <FormField label="Slug" value={form.slug} onChange={(v) => updateField("slug", v)} required />
          <FormField label="Clinic email (optional)" value={form.email} onChange={(v) => updateField("email", v)} type="email" />

          <div style={{ gridColumn: "1 / -1", fontSize: 13, fontWeight: 600, color: "#e5e7eb", marginTop: 8 }}>
            First Owner login (this is how the clinic signs in)
          </div>
          <FormField label="Owner first name" value={form.ownerFirstName} onChange={(v) => updateField("ownerFirstName", v)} required />
          <FormField label="Owner last name" value={form.ownerLastName} onChange={(v) => updateField("ownerLastName", v)} required />
          <FormField label="Owner email" value={form.ownerEmail} onChange={(v) => updateField("ownerEmail", v)} type="email" required />
          <FormField label="Owner username" value={form.ownerUsername} onChange={(v) => updateField("ownerUsername", v)} required />
          <FormField label="Owner password" value={form.ownerPassword} onChange={(v) => updateField("ownerPassword", v)} type="password" required />

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
              {creating ? "Creating..." : "Create tenant"}
            </button>
          </div>
        </form>
      )}

      {editingTenant && (
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
          <div style={{ gridColumn: "1 / -1", fontSize: 13, color: "#9ca3af" }}>Editing {editingTenant.name}</div>
          <FormField label="Clinic name" value={editForm.name} onChange={(v) => setEditForm({ ...editForm, name: v })} required />
          <FormField label="Slug" value={editForm.slug} onChange={(v) => setEditForm({ ...editForm, slug: v })} required />
          <FormField label="Clinic email (optional)" value={editForm.email} onChange={(v) => setEditForm({ ...editForm, email: v })} type="email" />

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
              onClick={() => setEditingTenant(null)}
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
                <Link href={`/platform/tenants/${t.id}/users`} style={{ color: "#93c5fd", marginRight: 8 }}>
                  Manage Users
                </Link>
                <button disabled={busyId === t.id} onClick={() => openEdit(t)}>
                  Edit
                </button>
                {t.status === "Active" && (
                  <button disabled={busyId === t.id} onClick={() => handleSuspend(t)} style={{ marginLeft: 8 }}>
                    Suspend
                  </button>
                )}
                {t.status === "Suspended" && (
                  <button disabled={busyId === t.id} onClick={() => handleReactivate(t)} style={{ marginLeft: 8 }}>
                    Reactivate
                  </button>
                )}
                {t.status !== "Archived" && (
                  <button disabled={busyId === t.id} onClick={() => handleArchive(t)} style={{ marginLeft: 8 }}>
                    Archive
                  </button>
                )}
                {t.status === "Archived" && (
                  <button
                    disabled={busyId === t.id}
                    onClick={() => handleDelete(t)}
                    style={{ marginLeft: 8, color: "#f87171" }}
                  >
                    Delete
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
