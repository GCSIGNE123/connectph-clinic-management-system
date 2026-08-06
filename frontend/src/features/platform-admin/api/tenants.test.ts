import { describe, expect, it } from "vitest";
import { filterTenants, toggleFlag, type Tenant, type FeatureFlag } from "./tenants";

const tenants: Tenant[] = [
  {
    id: "1", name: "PHASE15-TEST-Clinic-A", slug: "phase15-test-clinic-a", email: "a@phase15test.dev",
    status: "Active", suspended_at: null, suspended_reason: null, archived_at: null, created_at: "2026-01-01",
  },
  {
    id: "2", name: "CONNECT.PH Demo Clinic", slug: "connect-ph-demo", email: "demo@connectph.dev",
    status: "Active", suspended_at: null, suspended_reason: null, archived_at: null, created_at: "2026-01-01",
  },
];

describe("filterTenants", () => {
  it("returns all tenants for an empty query", () => {
    expect(filterTenants(tenants, "")).toHaveLength(2);
  });

  it("filters by name case-insensitively", () => {
    const result = filterTenants(tenants, "demo");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("2");
  });

  it("filters by slug", () => {
    const result = filterTenants(tenants, "phase15-test-clinic-a");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("1");
  });

  it("filters by email", () => {
    const result = filterTenants(tenants, "connectph.dev");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("2");
  });

  it("returns empty array when nothing matches", () => {
    expect(filterTenants(tenants, "nonexistent")).toHaveLength(0);
  });
});

describe("toggleFlag", () => {
  const flags: FeatureFlag[] = [
    { feature_key: "appointments", is_enabled: true },
    { feature_key: "laboratory", is_enabled: true },
  ];

  it("flips only the targeted flag", () => {
    const result = toggleFlag(flags, "appointments");
    expect(result.find((f) => f.feature_key === "appointments")?.is_enabled).toBe(false);
    expect(result.find((f) => f.feature_key === "laboratory")?.is_enabled).toBe(true);
  });

  it("does not mutate the original array", () => {
    const result = toggleFlag(flags, "appointments");
    expect(result).not.toBe(flags);
    expect(flags.find((f) => f.feature_key === "appointments")?.is_enabled).toBe(true);
  });
});
