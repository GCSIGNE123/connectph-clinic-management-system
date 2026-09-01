import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { resolveRecordDateRange } from "@/lib/date-range";

// Real system time throughout (not frozen) - `resolveRecordDateRange` itself
// is already thoroughly tested against fixed dates in `@/lib/date-range.test.ts`;
// here we only need the component to call it correctly, so computing the
// expected value the same way at test-run time avoids the flakiness of
// combining fake timers with `userEvent`.

describe("RecordDateRangeFilter", () => {
  it("renders All/Today/This Week/This Month/Custom as the preset options", () => {
    render(<RecordDateRangeFilter onApply={vi.fn()} />);
    const select = screen.getByLabelText("Date range preset") as HTMLSelectElement;
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(labels).toEqual(["All", "Today", "This Week", "This Month", "Custom"]);
  });

  it("applies immediately with the resolved range when Today is selected", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "today");

    expect(onApply).toHaveBeenCalledWith(resolveRecordDateRange("today"));
  });

  it("applies immediately with the resolved Monday-Sunday range when This Week is selected", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "this_week");

    expect(onApply).toHaveBeenCalledWith(resolveRecordDateRange("this_week"));
  });

  it("applies immediately with the resolved calendar-month range when This Month is selected", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "this_month");

    expect(onApply).toHaveBeenCalledWith(resolveRecordDateRange("this_month"));
  });

  it("Custom shows From/To inputs and an Apply button, and does not call onApply until Apply is clicked", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "custom");
    expect(screen.getByLabelText("Start date")).toBeInTheDocument();
    expect(screen.getByLabelText("End date")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
  });

  it("Custom applies the entered range once Apply is clicked", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "custom");
    await user.type(screen.getByLabelText("Start date"), "2026-01-01");
    await user.type(screen.getByLabelText("End date"), "2026-01-31");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onApply).toHaveBeenCalledWith({ dateFrom: "2026-01-01", dateTo: "2026-01-31" });
  });

  it("Custom rejects From > To with an inline error, and never calls onApply", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "custom");
    await user.type(screen.getByLabelText("Start date"), "2026-02-01");
    await user.type(screen.getByLabelText("End date"), "2026-01-01");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByText(/from date must be before or equal/i)).toBeInTheDocument();
  });

  it("Custom rejects a missing bound with an inline error", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "custom");
    await user.type(screen.getByLabelText("Start date"), "2026-02-01");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByText(/select both a from and to date/i)).toBeInTheDocument();
  });

  it("switching back to All applies an unfiltered (empty) range, resetting a previous Custom selection", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<RecordDateRangeFilter onApply={onApply} defaultPreset="today" />);

    await user.selectOptions(screen.getByLabelText("Date range preset"), "custom");
    await user.type(screen.getByLabelText("Start date"), "2026-01-01");
    await user.type(screen.getByLabelText("End date"), "2026-01-31");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    onApply.mockClear();

    await user.selectOptions(screen.getByLabelText("Date range preset"), "all");

    expect(onApply).toHaveBeenCalledWith({});
    // Custom inputs disappear once a non-custom preset is selected again.
    expect(screen.queryByLabelText("Start date")).not.toBeInTheDocument();
  });

  it("respects a non-default initial preset (e.g. a page that defaults to Today, not All)", () => {
    render(<RecordDateRangeFilter onApply={vi.fn()} defaultPreset="today" />);
    expect(screen.getByLabelText("Date range preset")).toHaveValue("today");
  });
});
