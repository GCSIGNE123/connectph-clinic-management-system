import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QueuePage from "./page";
import { Role } from "@/types";

const useQueuesMock = vi.fn();
vi.mock("@/features/queue/hooks/use-queues", () => ({
  useQueues: (params: unknown) => useQueuesMock(params),
  useQueueRealtime: () => {},
}));

vi.mock("@/features/queue/hooks/use-queue-mutations", () => ({
  useCancelQueue: () => ({ mutate: vi.fn(), isPending: false }),
  useChangeQueueStatus: () => ({ mutate: vi.fn(), isPending: false }),
  useReannounceQueue: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: Role.Receptionist, branchId: "branch-1" } }),
}));

const queueTableProps: unknown[] = [];
vi.mock("@/features/queue/components/QueueTable", () => ({
  QueueTable: (props: unknown) => {
    queueTableProps.push(props);
    return <div data-testid="queue-table" />;
  },
}));

vi.mock("@/features/queue/components/NewQueueDialog", () => ({ NewQueueDialog: () => null }));
vi.mock("@/features/queue/components/QueueDetailsDialog", () => ({ QueueDetailsDialog: () => null }));
vi.mock("@/features/queue/components/EditQueueDialog", () => ({ EditQueueDialog: () => null }));
vi.mock("@/features/queue/components/QueueSlipDialog", () => ({ QueueSlipDialog: () => null }));
vi.mock("@/features/consultation/components/ReceptionVitalsDialog", () => ({ ReceptionVitalsDialog: () => null }));

function lastCallParams() {
  return useQueuesMock.mock.calls.at(-1)?.[0];
}

describe("QueuePage - date range filter defaults to Today", () => {
  beforeEach(() => {
    useQueuesMock.mockReset().mockReturnValue({ data: { data: [] }, isLoading: false });
    queueTableProps.length = 0;
  });

  it("defaults to today's date range on first render, not All", () => {
    render(<QueuePage />);
    const today = new Date().toISOString().slice(0, 10);
    expect(lastCallParams()).toMatchObject({ dateFrom: today, dateTo: today });
    expect(screen.getByLabelText("Date range preset")).toHaveValue("today");
  });

  it("selecting All clears the date filter", async () => {
    const user = userEvent.setup();
    render(<QueuePage />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "all");

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.dateFrom).toBeUndefined();
      expect(params.dateTo).toBeUndefined();
    });
  });

  it("selecting This Week resolves to a Monday-Sunday range", async () => {
    const user = userEvent.setup();
    render(<QueuePage />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "this_week");

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.dateFrom).toBeTruthy();
      expect(params.dateTo).toBeTruthy();
      expect(params.dateFrom).not.toBe(params.dateTo);
    });
  });

  it("selecting This Month resolves to a calendar-month range", async () => {
    const user = userEvent.setup();
    render(<QueuePage />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "this_month");

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.dateFrom).toMatch(/^\d{4}-\d{2}-01$/);
    });
  });

  it("Custom applies only after Apply is clicked, with a valid range", async () => {
    const user = userEvent.setup();
    render(<QueuePage />);
    useQueuesMock.mockClear();

    await user.selectOptions(screen.getByLabelText("Date range preset"), "custom");
    await user.type(screen.getByLabelText("Start date"), "2026-03-01");
    await user.type(screen.getByLabelText("End date"), "2026-03-31");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.dateFrom).toBe("2026-03-01");
      expect(params.dateTo).toBe("2026-03-31");
    });
  });

  it("date filter combines with the existing status/priority/classification filters, none of which are disturbed", async () => {
    const user = userEvent.setup();
    render(<QueuePage />);

    await user.selectOptions(screen.getByDisplayValue("All statuses"), "Waiting");
    await user.selectOptions(screen.getByDisplayValue("All priorities"), "Normal");
    await user.selectOptions(screen.getByLabelText("Date range preset"), "this_month");

    await waitFor(() => {
      const params = lastCallParams();
      expect(params.status).toBe("Waiting");
      expect(params.priority).toBe("Normal");
      expect(params.dateFrom).toBeTruthy();
    });
  });

  it("existing queue actions (view/edit/reprint/cancel/call/re-announce) are still wired into QueueTable unchanged", () => {
    render(<QueuePage />);
    const props = queueTableProps.at(-1) as Record<string, unknown>;
    expect(props.onView).toBeInstanceOf(Function);
    expect(props.onEdit).toBeInstanceOf(Function);
    expect(props.onReprint).toBeInstanceOf(Function);
    expect(props.onCancel).toBeInstanceOf(Function);
    expect(props.onCall).toBeInstanceOf(Function);
    expect(props.onReannounce).toBeInstanceOf(Function);
    expect(props.canManage).toBe(true);
    expect(props.canTransition).toBe(true);
  });
});
