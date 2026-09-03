import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { SessionExpiredListener } from "./SessionExpiredListener";
import { SESSION_EXPIRED_EVENT } from "@/lib/api-client";

describe("SessionExpiredListener", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("navigates to /login when SESSION_EXPIRED_EVENT fires", () => {
    const originalHref = window.location.href;
    // jsdom's `window.location` is not directly assignable to in newer
    // versions - redefine it as a writable property, same technique used by
    // `lib/api-url.test.ts` for a comparable `window.location` swap.
    const setHref = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, set href(value: string) { setHref(value); } },
      writable: true,
      configurable: true,
    });

    render(<SessionExpiredListener />);
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));

    expect(setHref).toHaveBeenCalledWith("/login");

    Object.defineProperty(window, "location", { value: { href: originalHref }, writable: true, configurable: true });
  });

  it("does nothing on an unrelated event", () => {
    const setHref = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, set href(value: string) { setHref(value); } },
      writable: true,
      configurable: true,
    });

    render(<SessionExpiredListener />);
    window.dispatchEvent(new Event("some-other-event"));

    expect(setHref).not.toHaveBeenCalled();
  });
});
