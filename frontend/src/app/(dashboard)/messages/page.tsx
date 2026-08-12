"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/layout/EmptyState";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useConversation, useSendMessage, useStaffDirectory } from "@/features/messages/hooks/use-messages";

/**
 * Phase 20 (item 14): a minimal Receptionist <-> Doctor internal message
 * list - pick another staff member, see the conversation (polled every
 * 30s), send a plain-text message. No group chat, no attachments, no read
 * receipts beyond the boolean `readAt` (surfaced only as an unread count on
 * this page, not per-message ticks).
 */
export default function MessagesPage() {
  // Post-RC1 Phase 2.5 (BUG-031): `useSearchParams()` requires a Suspense
  // boundary during static generation, or `next build` (production build)
  // fails outright with a prerender error - `next dev` never surfaced this
  // since dev doesn't statically prerender. Vercel deploys always run a real
  // production build, so this was a genuine launch blocker for Vercel
  // readiness, not a cosmetic warning. Fix: isolate the `with=` query-param
  // read into its own child component wrapped in <Suspense>.
  return (
    <Suspense fallback={<MessagesPageFallback />}>
      <MessagesPageInner />
    </Suspense>
  );
}

function MessagesPageFallback() {
  return <p className="text-sm text-muted-foreground">Loading…</p>;
}

function MessagesPageInner() {
  const { data: currentUser } = useCurrentUser();
  const searchParams = useSearchParams();
  const [otherUserId, setOtherUserId] = useState<string>("");
  const [draft, setDraft] = useState("");

  // Item 6: arriving via `/messages?with={userId}` (from the notification
  // bell, or a specific unread-conversation entry) must open that
  // conversation directly - never force the "Select a staff member"
  // picker first. Runs whenever the `with` param changes (e.g. clicking a
  // different unread conversation from the bell while already on this
  // page).
  useEffect(() => {
    const withId = searchParams.get("with");
    if (withId) setOtherUserId(withId);
  }, [searchParams]);

  // Receptionist most commonly messages a Doctor and vice versa, but any
  // staff member may be picked - the recipient list is simply "everyone
  // else in this clinic" (via the minimal `/messages/staff-directory`
  // endpoint, not the Administrator/Owner-only `GET /users`).
  const { data: otherUsers, isLoading: usersLoading } = useStaffDirectory();

  const { data: conversation, isLoading: conversationLoading } = useConversation(otherUserId || undefined);
  const sendMessage = useSendMessage(otherUserId || undefined);

  const handleSend = () => {
    if (!draft.trim() || !otherUserId) return;
    sendMessage.mutate(draft.trim(), { onSuccess: () => setDraft("") });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Messages</h1>
        <p className="text-sm text-muted-foreground">Direct messages between clinic staff (e.g. Reception and Doctor).</p>
      </div>

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="max-w-sm">
            <label className="text-xs font-medium text-muted-foreground">Conversation with</label>
            <Select value={otherUserId} onChange={(e) => setOtherUserId(e.target.value)} disabled={usersLoading}>
              <option value="">Select a staff member…</option>
              {(otherUsers ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.fullName} ({u.role})
                </option>
              ))}
            </Select>
          </div>

          {!otherUserId ? (
            <EmptyState title="No conversation selected" description="Pick a staff member above to view or start a conversation." />
          ) : conversationLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-3">
              <div className="max-h-96 space-y-2 overflow-y-auto rounded-md border border-border p-3">
                {conversation && conversation.items.length > 0 ? (
                  conversation.items.map((m) => (
                    <div
                      key={m.id}
                      className={`max-w-[80%] rounded-md p-2 text-sm ${
                        m.senderId === currentUser?.id ? "ml-auto bg-primary text-primary-foreground" : "bg-muted"
                      }`}
                    >
                      <p>{m.body}</p>
                      <p className="mt-1 text-[10px] opacity-70">{new Date(m.createdAt).toLocaleString()}</p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">No messages yet. Say hello.</p>
                )}
              </div>
              <div className="flex gap-2">
                <Textarea
                  rows={2}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Type a message…"
                  className="flex-1"
                />
                <Button type="button" onClick={handleSend} disabled={!draft.trim() || sendMessage.isPending}>
                  Send
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
