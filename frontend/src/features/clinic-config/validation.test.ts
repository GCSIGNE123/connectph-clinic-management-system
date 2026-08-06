import { describe, expect, it } from "vitest";
import { validateQueueSettingsForm } from "./validation";

describe("validateQueueSettingsForm", () => {
  it("accepts a valid configuration", () => {
    expect(
      validateQueueSettingsForm({ queue_prefix: "A", max_daily_queue: 200, reset_time: "00:00" })
    ).toBeNull();
  });

  it("rejects an empty prefix", () => {
    expect(
      validateQueueSettingsForm({ queue_prefix: "", max_daily_queue: 200, reset_time: "00:00" })
    ).toMatch(/prefix is required/i);
  });

  it("rejects a prefix longer than 10 characters", () => {
    expect(
      validateQueueSettingsForm({ queue_prefix: "TOOLONGPREFIX", max_daily_queue: 200, reset_time: "00:00" })
    ).toMatch(/10 characters/i);
  });

  it("rejects a non-positive max daily queue", () => {
    expect(
      validateQueueSettingsForm({ queue_prefix: "A", max_daily_queue: 0, reset_time: "00:00" })
    ).toMatch(/at least 1/i);
  });

  it("rejects a max daily queue over 10,000", () => {
    expect(
      validateQueueSettingsForm({ queue_prefix: "A", max_daily_queue: 10001, reset_time: "00:00" })
    ).toMatch(/10,000/);
  });

  it("rejects a malformed reset time", () => {
    expect(
      validateQueueSettingsForm({ queue_prefix: "A", max_daily_queue: 200, reset_time: "midnight" })
    ).toMatch(/HH:MM/);
  });
});
