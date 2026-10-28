/**
 * Native EventSource hook for one audit.
 *
 * - Frames are deduplicated by the service's monotonic `seq`.
 * - On a dropped connection the hook closes the source and reopens it with the
 *   last seen sequence (`?last_event_id=N`), so no frame is lost or replayed
 *   twice. The browser also sends the standard Last-Event-ID header on its own
 *   automatic retries; the API accepts both.
 * - Probe frames are buffered and flushed in small batches, because a live
 *   audit can emit thousands of pairs and one React render per pair is wasteful.
 */

import * as React from "react";

import type { AgentEvent, ProbeEvent } from "@/api-types";
import { streamUrl } from "@/lib/api";
import { parseStreamData } from "@/lib/stream";

export type StreamStatus = "connecting" | "open" | "reconnecting" | "done" | "error";

export interface AuditDone {
  audit_id: string;
  status: "completed" | "failed";
  error?: string | null;
  last_seq?: number;
}

export interface AuditStreamState {
  status: StreamStatus;
  agentEvents: AgentEvent[];
  probeEvents: ProbeEvent[];
  /** Total probe frames received, even after the on-screen buffer is capped. */
  probeCount: number;
  lastEventId: number;
  reconnects: number;
  error: string | null;
  done: AuditDone | null;
}

const MAX_AGENT_EVENTS = 600;
const MAX_PROBE_EVENTS = 4000;

const initialState: AuditStreamState = {
  status: "connecting",
  agentEvents: [],
  probeEvents: [],
  probeCount: 0,
  lastEventId: 0,
  reconnects: 0,
  error: null,
  done: null,
};

export interface UseAuditStreamOptions {
  /** Probe frames are flushed at most this often. 0 means every frame. */
  batchMs?: number;
  /** Injectable for tests; defaults to window.EventSource. */
  eventSourceFactory?: (url: string) => EventSource;
}

export function useAuditStream(
  auditId: string | undefined,
  options: UseAuditStreamOptions = {},
): AuditStreamState {
  const { batchMs = 90, eventSourceFactory } = options;
  const [state, setState] = React.useState<AuditStreamState>(initialState);

  const lastSeqRef = React.useRef(0);
  const pendingProbesRef = React.useRef<ProbeEvent[]>([]);
  const flushTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const doneRef = React.useRef(false);

  const flushProbes = React.useCallback(() => {
    if (flushTimerRef.current !== null) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    const pending = pendingProbesRef.current;
    if (pending.length === 0) return;
    pendingProbesRef.current = [];
    setState((previous) => {
      const merged = previous.probeEvents.concat(pending);
      return {
        ...previous,
        probeCount: previous.probeCount + pending.length,
        probeEvents:
          merged.length > MAX_PROBE_EVENTS
            ? merged.slice(merged.length - MAX_PROBE_EVENTS)
            : merged,
      };
    });
  }, []);

  React.useEffect(() => {
    if (!auditId) {
      setState({ ...initialState, status: "error", error: "missing audit id" });
      return;
    }

    doneRef.current = false;
    lastSeqRef.current = 0;
    pendingProbesRef.current = [];
    setState(initialState);

    let cancelled = false;
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const factory =
      eventSourceFactory ??
      ((url: string) => new window.EventSource(url));

    const scheduleProbeFlush = () => {
      if (batchMs <= 0) {
        flushProbes();
        return;
      }
      if (flushTimerRef.current !== null) return;
      flushTimerRef.current = setTimeout(flushProbes, batchMs);
    };

    const onFrame = (kind: "agent" | "probe") => (event: MessageEvent<string>) => {
      const parsed = parseStreamData(event.data, kind);
      if (!parsed) return;
      if (parsed.seq <= lastSeqRef.current) return;
      lastSeqRef.current = parsed.seq;
      setState((previous) => ({ ...previous, lastEventId: parsed.seq }));

      if (kind === "probe") {
        pendingProbesRef.current.push(parsed.data as ProbeEvent);
        scheduleProbeFlush();
        return;
      }
      setState((previous) => {
        const merged = previous.agentEvents.concat(parsed.data as AgentEvent);
        return {
          ...previous,
          agentEvents:
            merged.length > MAX_AGENT_EVENTS
              ? merged.slice(merged.length - MAX_AGENT_EVENTS)
              : merged,
        };
      });
    };

    const connect = () => {
      if (cancelled || doneRef.current) return;
      setState((previous) => ({
        ...previous,
        status: previous.lastEventId > 0 ? "reconnecting" : "connecting",
        error: null,
      }));
      source = factory(streamUrl(auditId, lastSeqRef.current));

      source.onopen = () => {
        attempt = 0;
        if (!cancelled) {
          setState((previous) => ({ ...previous, status: "open" }));
        }
      };

      source.addEventListener("agent", onFrame("agent") as EventListener);
      source.addEventListener("probe", onFrame("probe") as EventListener);
      source.addEventListener("done", (event) => {
        const done = parseDone((event as MessageEvent<string>).data);
        doneRef.current = true;
        flushProbes();
        source?.close();
        if (!cancelled) {
          setState((previous) => ({
            ...previous,
            status: done?.status === "failed" ? "error" : "done",
            done,
            error: done?.error ?? null,
          }));
        }
      });

      source.onerror = () => {
        if (cancelled || doneRef.current) return;
        source?.close();
        attempt += 1;
        setState((previous) => ({
          ...previous,
          status: "reconnecting",
          reconnects: previous.reconnects + 1,
          error: "connection lost; resuming from the last event",
        }));
        const delay = Math.min(8000, 400 * 2 ** Math.min(attempt - 1, 5));
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      if (flushTimerRef.current !== null) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
      source?.close();
    };
  }, [auditId, batchMs, eventSourceFactory, flushProbes]);

  return state;
}

function parseDone(raw: string): AuditDone | null {
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (typeof value.audit_id !== "string") return null;
    return {
      audit_id: value.audit_id,
      status: value.status === "failed" ? "failed" : "completed",
      error: typeof value.error === "string" ? value.error : null,
      last_seq: typeof value.last_seq === "number" ? value.last_seq : undefined,
    };
  } catch {
    return null;
  }
}
