import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import ClinicSettingsPage from "./page";
import { Role } from "@/types";

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: Role.Owner } }),
}));

vi.mock("@/lib/api-url", () => ({
  resolveMediaUrl: (path: string | null) => (path ? `http://api.test${path}` : null),
}));

vi.mock("@/components/layout/ThemeSettings", () => ({
  ThemeSettings: () => <div>theme settings</div>,
}));

let mockSettings: Record<string, unknown> = {
  id: "clinic-1", name: "Canora Medical Clinic & Laboratory", timezone: "Asia/Manila",
  language: "en", currency: "PHP", date_format: "MM/DD/YYYY", time_format: "12h", status: "Active",
  theme: "system", logo_url: null,
};

const mockGet = vi.fn();
const mockUploadFile = vi.fn();
const mockDelete = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    put: vi.fn(),
    patch: vi.fn(),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
  apiUploadFile: (...args: unknown[]) => mockUploadFile(...args),
  ApiError: class ApiError extends Error {},
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ClinicSettingsPage />
      </ToastProvider>
    </QueryClientProvider>
  );
}

async function openBrandingTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "branding" }));
}

describe("ClinicSettingsPage - Clinic Logo branding (Round 7)", () => {
  it("1: renders the Clinic Logo settings section with an empty state when unconfigured", async () => {
    mockGet.mockReset().mockResolvedValue({ ...mockSettings, logo_url: null });
    const user = userEvent.setup();
    renderPage();
    await openBrandingTab(user);

    expect(await screen.findByText("Clinic logo")).toBeInTheDocument();
    expect(screen.getByTestId("clinic-logo-not-configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload logo" })).toBeInTheDocument();
  });

  it("3: renders a preview of the current logo when configured", async () => {
    mockGet.mockReset().mockResolvedValue({ ...mockSettings, logo_url: "/media/clinic-logo/clinic-1/logo-abc.png" });
    const user = userEvent.setup();
    renderPage();
    await openBrandingTab(user);

    const img = await screen.findByAltText("Clinic logo");
    expect(img).toHaveAttribute("src", "http://api.test/media/clinic-logo/clinic-1/logo-abc.png");
    expect(screen.getByRole("button", { name: "Replace logo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove logo" })).toBeInTheDocument();
  });

  it("2/4: uploading a logo calls the real upload endpoint (upload works, replace works the same way)", async () => {
    mockGet.mockReset().mockResolvedValue({ ...mockSettings, logo_url: null });
    mockUploadFile.mockReset().mockResolvedValue({ ...mockSettings, logo_url: "/media/clinic-logo/clinic-1/logo-new.png" });
    const user = userEvent.setup();
    renderPage();
    await openBrandingTab(user);

    await screen.findByText("Clinic logo");
    const file = new File(["png-bytes"], "logo.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(mockUploadFile).toHaveBeenCalledWith("/clinic-settings/logo", expect.any(FormData)));
  });

  it("removing the logo calls the real delete endpoint", async () => {
    mockGet.mockReset().mockResolvedValue({ ...mockSettings, logo_url: "/media/clinic-logo/clinic-1/logo-abc.png" });
    mockDelete.mockReset().mockResolvedValue({ ...mockSettings, logo_url: null });
    const user = userEvent.setup();
    renderPage();
    await openBrandingTab(user);

    await user.click(await screen.findByRole("button", { name: "Remove logo" }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/clinic-settings/logo"));
  });

  it("5: an empty/no-logo state never fabricates a placeholder image", async () => {
    mockGet.mockReset().mockResolvedValue({ ...mockSettings, logo_url: null });
    const user = userEvent.setup();
    renderPage();
    await openBrandingTab(user);

    await screen.findByText("Clinic logo");
    expect(screen.queryByAltText("Clinic logo")).not.toBeInTheDocument();
  });
});
