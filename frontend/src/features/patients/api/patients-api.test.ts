import { beforeEach, describe, expect, it, vi } from "vitest";
import { patientsApi } from "./patients-api";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({ apiClient: { get: (...a: unknown[]) => getMock(...a) } }));

describe("patientsApi.list - YAKAP filter query string (Task #5)", () => {
  beforeEach(() => {
    getMock.mockReset().mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });
  });

  const urlOf = () => String(getMock.mock.calls.at(-1)?.[0]);

  it("omits is_yakap_beneficiary when the filter is unset (All Patients)", async () => {
    await patientsApi.list({ page: 1, pageSize: 10 });
    expect(urlOf()).not.toContain("is_yakap_beneficiary");
  });

  it("sends is_yakap_beneficiary=true for YAKAP", async () => {
    await patientsApi.list({ isYakapBeneficiary: true });
    expect(urlOf()).toContain("is_yakap_beneficiary=true");
  });

  it("sends is_yakap_beneficiary=false for Regular (false is not dropped)", async () => {
    await patientsApi.list({ isYakapBeneficiary: false });
    expect(urlOf()).toContain("is_yakap_beneficiary=false");
  });

  it("combines with search and pagination server-side params", async () => {
    await patientsApi.list({ isYakapBeneficiary: true, search: "Santos", page: 3, pageSize: 10 });
    const url = urlOf();
    expect(url).toContain("is_yakap_beneficiary=true");
    expect(url).toContain("q=Santos");
    expect(url).toContain("limit=10");
    expect(url).toContain("offset=20");
  });
});
