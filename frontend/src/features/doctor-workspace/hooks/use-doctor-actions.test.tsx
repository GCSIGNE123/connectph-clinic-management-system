import { describe, expect, it, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useCallPatient, useCompleteConsultation, useCancelVisit } from "./use-doctor-actions";
import { doctorWorkspaceKeys } from "@/features/doctor-workspace/hooks/use-doctor-dashboard";
import { visitKeys } from "@/features/visits/hooks/use-visits";
import { ToastProvider } from "@/components/ui/toast";

vi.mock("@/features/doctor-workspace/api/doctor-workspace-api", () => ({
  doctorWorkspaceApi: {
    call: vi.fn().mockResolvedValue({ queue_number: "A001" }),
    completeConsultation: vi.fn().mockResolvedValue({}),
    cancel: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock("@/lib/queue-announcer", () => ({ announceQueueNumber: vi.fn() }));

/** Phase 5B (P1, D4): a Doctor Workspace action that changes a Visit's
 * status must invalidate that visit's own detail query - the Visit
 * Details page has no other refresh mechanism (no WebSocket, no poll). */
describe("Doctor Workspace action -> Visit Details cache invalidation (Phase 5B)", () => {
  function setup() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");
    function wrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={client}>
          <ToastProvider>{children}</ToastProvider>
        </QueryClientProvider>
      );
    }
    return { client, invalidateSpy, wrapper };
  }

  it("useCompleteConsultation invalidates both doctorWorkspaceKeys.all and visitKeys.detail(visitId)", async () => {
    const { invalidateSpy, wrapper } = setup();
    const { result } = renderHook(() => useCompleteConsultation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("visit-123");
    });

    await waitFor(() => {
      const calledKeys = invalidateSpy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(calledKeys).toContain(JSON.stringify(doctorWorkspaceKeys.all));
      expect(calledKeys).toContain(JSON.stringify(visitKeys.detail("visit-123")));
    });
  });

  it("useCallPatient also invalidates the visit's own detail query, not just an unrelated visit", async () => {
    const { invalidateSpy, wrapper } = setup();
    const { result } = renderHook(() => useCallPatient(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync("visit-abc");
    });

    await waitFor(() => {
      const calledKeys = invalidateSpy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(calledKeys).toContain(JSON.stringify(visitKeys.detail("visit-abc")));
      // Must be scoped to the acted-upon visit, not some other visit id.
      expect(calledKeys).not.toContain(JSON.stringify(visitKeys.detail("some-other-visit")));
    });
  });

  it("useCancelVisit invalidates the correct visit's detail query from its {visitId, reason} payload", async () => {
    const { invalidateSpy, wrapper } = setup();
    const { result } = renderHook(() => useCancelVisit(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ visitId: "visit-xyz", reason: "Patient left" });
    });

    await waitFor(() => {
      const calledKeys = invalidateSpy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
      expect(calledKeys).toContain(JSON.stringify(visitKeys.detail("visit-xyz")));
    });
  });
});
