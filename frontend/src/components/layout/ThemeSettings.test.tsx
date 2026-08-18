import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ThemeProvider } from "next-themes";
import { ThemeSettings } from "./ThemeSettings";

/** next-themes reads `window.matchMedia` to resolve "system" - jsdom has
 * no real implementation, so a minimal stub is needed for the provider to
 * mount at all. Scoped to this file rather than the shared vitest setup,
 * since no other test currently exercises next-themes. */
function stubMatchMedia(prefersDark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: prefersDark && query === "(prefers-color-scheme: dark)",
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

function renderThemeSettings() {
  return render(
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="connectph-theme">
      <ThemeSettings />
    </ThemeProvider>,
  );
}

describe("ThemeSettings", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
    stubMatchMedia(false);
  });

  it("displays the Appearance/Theme control with Light, Dark, and System options", async () => {
    renderThemeSettings();
    expect(screen.getByText("Theme")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: /light/i })).toBeInTheDocument();
      expect(screen.getByRole("radio", { name: /dark/i })).toBeInTheDocument();
      expect(screen.getByRole("radio", { name: /system/i })).toBeInTheDocument();
    });
  });

  it("selecting Dark persists the preference to localStorage", async () => {
    renderThemeSettings();
    fireEvent.click(await screen.findByRole("radio", { name: /dark/i }));
    await waitFor(() => expect(localStorage.getItem("connectph-theme")).toBe("dark"));
  });

  it("selecting Light persists the preference to localStorage", async () => {
    renderThemeSettings();
    fireEvent.click(await screen.findByRole("radio", { name: /light/i }));
    await waitFor(() => expect(localStorage.getItem("connectph-theme")).toBe("light"));
  });

  it("selecting System persists the preference to localStorage", async () => {
    renderThemeSettings();
    fireEvent.click(await screen.findByRole("radio", { name: /dark/i }));
    await waitFor(() => expect(localStorage.getItem("connectph-theme")).toBe("dark"));

    fireEvent.click(await screen.findByRole("radio", { name: /system/i }));
    await waitFor(() => expect(localStorage.getItem("connectph-theme")).toBe("system"));
  });

  it("selecting Dark applies the dark class to the document root", async () => {
    renderThemeSettings();
    fireEvent.click(await screen.findByRole("radio", { name: /dark/i }));
    await waitFor(() => expect(document.documentElement.classList.contains("dark")).toBe(true));
  });

  it("selecting Light removes the dark class from the document root", async () => {
    renderThemeSettings();
    fireEvent.click(await screen.findByRole("radio", { name: /dark/i }));
    await waitFor(() => expect(document.documentElement.classList.contains("dark")).toBe(true));

    fireEvent.click(await screen.findByRole("radio", { name: /light/i }));
    await waitFor(() => expect(document.documentElement.classList.contains("dark")).toBe(false));
  });
});
