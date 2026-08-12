"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TvDisplayData } from "@/features/tv-display/types";
import { fetchPublicTvDisplay } from "@/features/tv-display/api/tv-display-api";
import { getApiBaseUrl } from "@/lib/api-url";
import {
  type BackoffState,
  initialBackoffState,
  nextDelayMs,
  onClose,
  onManualClose,
  onOpen,
} from "@/features/tv-display/hooks/use-connection-backoff";

function wsUrl(clinicId: string, publicSlug: string): string {
  const apiUrl = getApiBaseUrl();
  const wsBase = apiUrl.replace(/^http/, "ws").replace(/\/api\/v1$/, "");
  // Public displays have no JWT. The `public_slug` itself is passed as the
  // `token` query param and doubles as the WS credential for this one
  // connection type - see `ws_queues.py`'s module docstring (Phase 13) for
  // the full rationale (extended, not duplicated, to accept either a real
  // access token OR a known-public display slug).
  return `${wsBase}/api/v1/ws/queues/${clinicId}?token=${encodeURIComponent(publicSlug)}`;
}

/** Post-RC1 (short TV display URL): `identifier` (the hook's own
 * parameter, i.e. whatever the browser's URL contained - the real
 * `public_slug`, OR the new short `short_code` alias) is only ever used
 * for the REST fetch. The WebSocket connection deliberately always uses
 * `wsAuthSlug` from the snapshot response instead - the row's real,
 * high-entropy `public_slug` - never the raw `identifier`. This keeps
 * `ws_queues.py`'s WS auth path completely untouched by the short-code
 * feature: it still only ever accepts the true 192-bit slug, exactly as
 * before, regardless of which URL got the browser here. */
export function resolveWsToken(identifier: string, wsAuthSlug: string | null): string {
  return wsAuthSlug ?? identifier;
}

/**
 * Subscribes to the existing `/ws/queues/{clinicId}` channel (Phase 5/7's
 * realtime architecture, unchanged) for a public TV display, and re-fetches
 * the full display snapshot on ANY event rather than trying to apply a
 * partial patch from the event payload.
 *
 * Why re-fetch instead of patching in place: `queue.status_changed`'s
 * payload (a `QueueDetail`) carries enough fields to patch a single row,
 * but the display also needs to recompute which tickets fall in/out of
 * "Now Serving" vs "Next N Waiting" (ordering, `queue_size` truncation,
 * ACTIVE_QUEUE_STATUSES membership) and to keep the ticking `server_time`
 * fresh - a full re-fetch is simpler, always correct, and cheap (one small
 * JSON response) compared to re-implementing that filtering/ordering logic
 * twice (once on the backend, once again in the browser).
 */
export function useTvDisplayRealtime(publicSlug: string, pollIntervalSeconds: number) {
  const [data, setData] = useState<TvDisplayData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState<BackoffState>(initialBackoffState());
  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);

  const refetch = useCallback(async () => {
    try {
      const snapshot = await fetchPublicTvDisplay(publicSlug);
      if (!cancelledRef.current) {
        setData(snapshot);
        setError(null);
      }
      return snapshot;
    } catch (err) {
      if (!cancelledRef.current) setError(err instanceof Error ? err.message : "Failed to load display");
      return null;
    }
  }, [publicSlug]);

  useEffect(() => {
    cancelledRef.current = false;

    // Resolve the clinic id AND the real WS token from the first
    // successful snapshot fetch, then open the WS. If the initial fetch
    // fails (bad slug/code, backend down), we still retry via the poll
    // fallback below.
    let clinicId: string | null = null;
    let wsToken: string | null = null;

    const connect = () => {
      if (cancelledRef.current || !clinicId || !wsToken) return;
      let socket: WebSocket;
      try {
        socket = new WebSocket(wsUrl(clinicId, wsToken));
      } catch {
        setConnection((s) => onClose(s));
        scheduleReconnect();
        return;
      }
      socketRef.current = socket;
      setConnection((s) => (s.status === "open" ? s : { ...s, status: "connecting" }));

      socket.onopen = () => setConnection((s) => onOpen(s));
      socket.onmessage = () => {
        void refetch();
      };
      socket.onclose = () => {
        if (cancelledRef.current) return;
        setConnection((s) => onClose(s));
        scheduleReconnect();
      };
      socket.onerror = () => {
        socket.close();
      };
    };

    const scheduleReconnect = () => {
      if (cancelledRef.current) return;
      setConnection((current) => {
        const delay = nextDelayMs(current.attempt);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(connect, delay);
        return current;
      });
    };

    const bootstrap = async () => {
      const snapshot = await refetch();
      if (snapshot) {
        clinicId = snapshot.wsChannelClinicId;
        wsToken = resolveWsToken(publicSlug, snapshot.wsAuthSlug);
        connect();
      } else {
        scheduleReconnect();
      }
    };

    void bootstrap();

    // Belt-and-suspenders poll fallback (mirrors `useQueues`'s pattern from
    // Phase 5) - the WS is the primary update path, but if it silently
    // fails to reconnect (e.g. a proxy strips WS upgrades), the display
    // still self-heals within `pollIntervalSeconds` instead of freezing
    // forever, which would be unacceptable for an unattended kiosk.
    const pollTimer = setInterval(() => void refetch(), Math.max(5, pollIntervalSeconds) * 1000);

    return () => {
      cancelledRef.current = true;
      setConnection((s) => onManualClose(s));
      if (timerRef.current) clearTimeout(timerRef.current);
      clearInterval(pollTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [publicSlug, pollIntervalSeconds, refetch]);

  return { data, error, connectionStatus: connection.status };
}
