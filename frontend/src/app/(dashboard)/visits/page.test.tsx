import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import VisitsPage from "./page";

const useVisitsMock = vi.fn();
vi.mock("@/features/visits/hooks/use-visits", () => ({
  useVisits: (params: unknown) => useVisitsMock(params),
}));

vi.mock("@/features/visits/components/VisitTable", () => ({
  VisitTable: () => <div data-testid="visit-table" />,
}));

function lastCallParams() {
  return useVisitsMock.mock.calls.at(-1)?.[0];
}

describe("VisitsPage - date range filter", () => {
  beforeEach(() => {
    useVisitsMock.mockReset().mockReturnValue({ data: { data: [], meta: undefined }, isLoading: false, isFetching: false });
  });

  it("defaults to today's date range (Today preset), not All", () => {
    render(<VisitsPage />);
    const today = new Date().toISOString().slice(0, 10);
    expect(lastCallParams()).toMatchObject({ dateFrom: today, dateTo: today });
  });

  it("selecting This Month updates the query params passed to useVisits", async () => {
    const user = userEvent.setup();
    render(<VisitsPage />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "this_month");

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.dateFrom).toMatch(/^\d{4}-\d{2}-01$/);
      expect(params.dateTo).toBeTruthy();
    });
  });

  it("selecting All clears the date filter", async () => {
    const user = userEvent.setup();
    render(<VisitsPage />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "all");

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.dateFrom).toBeUndefined();
      expect(params.dateTo).toBeUndefined();
    });
  });

  it("date filter combines with the existing status filter - both are present in the same query", async () => {
    const user = userEvent.setup();
    render(<VisitsPage />);

    await user.selectOptions(screen.getByDisplayValue("All statuses"), "Waiting");
    await user.selectOptions(screen.getByLabelText("Date range preset"), "this_week");

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.status).toBe("Waiting");
      expect(params.dateFrom).toBeTruthy();
      expect(params.dateTo).toBeTruthy();
    });
  });

  it("Custom range only applies once Apply is clicked, and is rejected when From > To", async () => {
    const user = userEvent.setup();
    render(<VisitsPage />);
    useVisitsMock.mockClear();

    await user.selectOptions(screen.getByLabelText("Date range preset"), "custom");
    await user.type(screen.getByLabelText("Start date"), "2026-02-01");
    await user.type(screen.getByLabelText("End date"), "2026-01-01");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    // Invalid range - useVisits must never have been called with it.
    expect(useVisitsMock.mock.calls.every((c) => c[0].dateFrom !== "2026-02-01")).toBe(true);

    await user.clear(screen.getByLabelText("End date"));
    await user.type(screen.getByLabelText("End date"), "2026-02-15");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.dateFrom).toBe("2026-02-01");
      expect(params.dateTo).toBe("2026-02-15");
    });
  });
});
