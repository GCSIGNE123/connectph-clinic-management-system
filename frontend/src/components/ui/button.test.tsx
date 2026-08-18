import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "./button";

/**
 * Regression coverage for the `asChild` bug found while verifying the
 * Doctor E-Signature feature: `Slot` (see `components/ui/slot.tsx`) only
 * clones a SINGLE valid React element - previously `Button` always passed
 * it two children (`{isLoading ? <Loader2/> : null}` plus `children`),
 * which turns `Slot`'s `children` prop into an array,
 * `React.isValidElement` on that array is false, and `Slot` silently
 * rendered nothing at all for EVERY `asChild` usage, loading or not.
 */
describe("Button", () => {
  it("renders normally as a <button>", () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole("button", { name: "Click me" });
    expect(btn.tagName).toBe("BUTTON");
    expect(btn).not.toBeDisabled();
  });

  it("shows a spinner and disables itself when isLoading", () => {
    render(<Button isLoading>Saving</Button>);
    const btn = screen.getByRole("button", { name: "Saving" });
    expect(btn).toBeDisabled();
    expect(btn.querySelector("svg")).toBeInTheDocument();
  });

  it("asChild renders the single child element itself (e.g. a Link), not a wrapping <button>", () => {
    render(
      <Button asChild>
        <a href="/somewhere">Go</a>
      </Button>
    );
    const link = screen.getByRole("link", { name: "Go" });
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).toBe("/somewhere");
    // Regression: this used to render nothing at all.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("asChild + isLoading still renders the child (documented contract: asChild skips the spinner/disabled injection, it never crashes or vanishes)", () => {
    render(
      <Button asChild isLoading>
        <a href="/somewhere">Go</a>
      </Button>
    );
    const link = screen.getByRole("link", { name: "Go" });
    expect(link).toBeInTheDocument();
    // No spinner injected for asChild - the child owns its own content.
    expect(link.querySelector("svg")).not.toBeInTheDocument();
  });
});
