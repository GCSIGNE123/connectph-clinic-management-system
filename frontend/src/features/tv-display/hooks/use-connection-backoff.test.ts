import { describe, expect, test } from "vitest";
import {
  initialBackoffState,
  nextDelayMs,
  onClose,
  onManualClose,
  onOpen,
} from "./use-connection-backoff";

describe("connection backoff state machine", () => {
  test("starts in 'connecting' with attempt 0", () => {
    expect(initialBackoffState()).toEqual({ status: "connecting", attempt: 0 });
  });

  test("onOpen resets to 'open' with attempt 0", () => {
    const state = onOpen({ status: "reconnecting", attempt: 4 });
    expect(state).toEqual({ status: "open", attempt: 0 });
  });

  test("onClose moves to 'reconnecting' and increments attempt", () => {
    const s1 = onClose(initialBackoffState());
    expect(s1).toEqual({ status: "reconnecting", attempt: 1 });
    const s2 = onClose(s1);
    expect(s2).toEqual({ status: "reconnecting", attempt: 2 });
  });

  test("onManualClose moves to 'closed' and resets attempt", () => {
    expect(onManualClose({ status: "reconnecting", attempt: 5 })).toEqual({ status: "closed", attempt: 0 });
  });

  test("nextDelayMs grows with attempt count but stays capped", () => {
    const d0 = nextDelayMs(0);
    const d5 = nextDelayMs(5);
    const d20 = nextDelayMs(20); // should be clamped, not literally huge
    expect(d0).toBeGreaterThanOrEqual(500);
    expect(d0).toBeLessThan(2000);
    expect(d5).toBeGreaterThanOrEqual(500);
    expect(d20).toBeLessThanOrEqual(30500);
  });

  test("nextDelayMs never returns a negative or zero delay", () => {
    for (let attempt = 0; attempt < 10; attempt++) {
      expect(nextDelayMs(attempt)).toBeGreaterThan(0);
    }
  });
});
