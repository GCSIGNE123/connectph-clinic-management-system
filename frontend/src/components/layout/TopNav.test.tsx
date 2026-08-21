import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TopNav } from "./TopNav";

function renderTopNav() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TopNav />
    </QueryClientProvider>
  );
}

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

let mockRole = "Owner";
vi.mock("@/features/auth/hooks/use-current-user", () => ({
  useCurrentUser: () => ({ data: { role: mockRole } }),
}));

vi.mock("@/features/messages/hooks/use-messages", () => ({
  useUnreadMessageCount: () => ({ data: 0 }),
  useUnreadByConversation: () => ({ data: [] }),
}));

let mockUnreadCount = 0;
let mockNotifications: { id: string; title: string; body: string; is_read: boolean; entity_type?: string | null; entity_id?: string | null }[] = [];
const mockMarkRead = vi.fn();
const mockMarkAllRead = vi.fn();

vi.mock("@/features/notifications/hooks/use-notifications", () => ({
  useUnreadNotificationCount: (enabled: boolean) => ({ data: enabled ? mockUnreadCount : undefined }),
  useNotificationList: (enabled: boolean) => ({ data: enabled ? { items: mockNotifications, total: mockNotifications.length } : undefined }),
  useMarkNotificationRead: () => ({ mutate: mockMarkRead }),
  useMarkAllNotificationsRead: () => ({ mutate: mockMarkAllRead }),
}));

function reset() {
  mockPush.mockReset();
  mockMarkRead.mockReset();
  mockMarkAllRead.mockReset();
  mockUnreadCount = 0;
  mockNotifications = [];
}

describe("TopNav inventory notification bell", () => {
  it("displays the unread inventory notification count", () => {
    mockRole = "Receptionist";
    reset();
    mockUnreadCount = 3;
    renderTopNav();

    expect(screen.getByLabelText("3 unread inventory notifications")).toBeInTheDocument();
  });

  it("hides the inventory bell entirely for a role outside INVENTORY_NOTIFICATION_ROLES", () => {
    mockRole = "Cashier";
    reset();
    mockUnreadCount = 5;
    renderTopNav();

    expect(screen.queryByLabelText(/inventory notification/i)).not.toBeInTheDocument();
  });

  it("renders the notification list with unread/read visually distinguished", async () => {
    mockRole = "Doctor";
    reset();
    mockNotifications = [
      { id: "n1", title: "Medicine Expiring Soon", body: "Amoxicillin, Batch AMX-1, expires in 7 days.", is_read: false },
      { id: "n2", title: "Medicine Expired", body: "Paracetamol, Batch P-1, expired.", is_read: true },
    ];
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByLabelText("Inventory notifications"));

    expect(screen.getByText("Medicine Expiring Soon")).toBeInTheDocument();
    expect(screen.getByText("Medicine Expired")).toBeInTheDocument();
  });

  it("shows an empty state when there are no notifications", async () => {
    mockRole = "Doctor";
    reset();
    mockNotifications = [];
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByLabelText("Inventory notifications"));
    expect(screen.getByText("No notifications")).toBeInTheDocument();
  });

  it("marks a notification read and navigates to its medicine on click", async () => {
    mockRole = "Doctor";
    reset();
    mockNotifications = [
      { id: "n1", title: "Medicine Expiring Soon", body: "Amoxicillin...", is_read: false, entity_type: "medicine", entity_id: "med-42" },
    ];
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByLabelText("Inventory notifications"));
    await user.click(screen.getByText("Medicine Expiring Soon"));

    expect(mockMarkRead).toHaveBeenCalledWith("n1");
    expect(mockPush).toHaveBeenCalledWith("/medicines/med-42");
  });

  it("does not re-mark an already-read notification, but still navigates", async () => {
    mockRole = "Doctor";
    reset();
    mockNotifications = [
      { id: "n1", title: "Medicine Expired", body: "...", is_read: true, entity_type: "medicine", entity_id: "med-9" },
    ];
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByLabelText("Inventory notifications"));
    await user.click(screen.getByText("Medicine Expired"));

    expect(mockMarkRead).not.toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith("/medicines/med-9");
  });

  it("lets the user mark all notifications read", async () => {
    mockRole = "Owner";
    reset();
    mockNotifications = [{ id: "n1", title: "Medicine Expired", body: "...", is_read: false }];
    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByLabelText("Inventory notifications"));
    await user.click(screen.getByText("Mark all read"));

    expect(mockMarkAllRead).toHaveBeenCalled();
  });
});
