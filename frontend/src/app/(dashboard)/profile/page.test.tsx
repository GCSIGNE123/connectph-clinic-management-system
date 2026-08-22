import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import ProfilePage from "./page";
import { Role } from "@/types";

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

let mockUser: Record<string, unknown> = {
  id: "user-1", email: "maria@example.com", firstName: "Maria", lastName: "Cruz",
  role: Role.Laboratory, isActive: true, hasSignature: false, licenseNumber: null,
};

vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: mockUser }),
  authKeys: { currentUser: ["auth", "current-user"] },
}));

const mockGetSignatureBlob = vi.fn();
vi.mock("@/features/auth/api/auth-api", () => ({
  authApi: {
    getSignatureBlob: (...args: unknown[]) => mockGetSignatureBlob(...args),
    uploadSignature: vi.fn(),
    removeSignature: vi.fn(),
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
  },
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ProfilePage />
      </ToastProvider>
    </QueryClientProvider>
  );
}

describe("ProfilePage - Med Tech In Charge signature (Round 6)", () => {
  it("1: renders the Med Tech signature settings section for a Laboratory-role user", () => {
    mockUser = { ...mockUser, role: Role.Laboratory };
    renderPage();
    expect(screen.getByText("Med Tech In Charge E-Signature")).toBeInTheDocument();
    expect(screen.getByTestId("signature-not-configured")).toBeInTheDocument();
  });

  it("also renders for Owner/Administrator (the same roles allowed to release Laboratory results)", () => {
    mockUser = { ...mockUser, role: Role.Owner };
    renderPage();
    expect(screen.getByText("Med Tech In Charge E-Signature")).toBeInTheDocument();
  });

  it("does not render the Med Tech signature section for an unrelated role (e.g. Receptionist)", () => {
    mockUser = { ...mockUser, role: Role.Receptionist };
    renderPage();
    expect(screen.queryByText("Med Tech In Charge E-Signature")).not.toBeInTheDocument();
  });
});
