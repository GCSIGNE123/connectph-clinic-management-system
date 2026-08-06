/**
 * Pure reconnect/exponential-backoff state machine, isolated from the
 * WebSocket plumbing so it's independently unit-testable (see
 * `use-connection-backoff.test.ts`).
 *
 * This is the FIRST reconnect-on-disconnect logic in the project - the
 * existing `features/queue/hooks/use-queues.ts::useQueueRealtime` (Phase 5)
 * has no reconnect logic at all; it opens one socket and, if it drops,
 * relies entirely on `useQueues`'s 30s `refetchInterval` poll as the
 * fallback, with no attempt to re-establish the socket itself. A kiosk TV
 * display left running for days cannot rely on a human noticing a stalled
 * poll-only fallback, so this phase adds real reconnect-with-backoff and
 * documents it here as new, not a refactor of existing behavior.
 */

export type ConnectionStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface BackoffState {
  status: ConnectionStatus;
  attempt: number;
}

const MIN_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;

/** Full-jitter exponential backoff, capped at `MAX_DELAY_MS`. */
export function nextDelayMs(attempt: number): number {
  const base = Math.min(MAX_DELAY_MS, MIN_DELAY_MS * 2 ** attempt);
  return Math.floor(Math.random() * base) + MIN_DELAY_MS / 2;
}

export function initialBackoffState(): BackoffState {
  return { status: "connecting", attempt: 0 };
}

export function onOpen(_state: BackoffState): BackoffState {
  return { status: "open", attempt: 0 };
}

export function onClose(state: BackoffState): BackoffState {
  return { status: "reconnecting", attempt: state.attempt + 1 };
}

export function onManualClose(_state: BackoffState): BackoffState {
  return { status: "closed", attempt: 0 };
}
