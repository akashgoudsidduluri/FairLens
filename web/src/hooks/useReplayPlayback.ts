/**
 * Offline playback of a recorded audit.
 *
 * A replay is a finished recording, not a live SSE connection: all frames are
 * already in memory. This hook reveals them at the recorded wall-clock pace so
 * the twin stream, evidence meter and agent lanes animate exactly as they did
 * during the audit, without contacting a sandbox or starting an API job.
 *
 * The timeline is reconstructed from the event order and the recorded start and
 * completion timestamps. Events are spread evenly across that window; probe
 * frames carry no per-pair timestamp, so even spacing is the honest choice and
 * avoids inventing latency data we do not have.
 */

import * as React from "react";

import type {
  AgentEvent,
  AuditRecord,
  ProbeEvent,
  ReplayFile,
  StreamEvent,
} from "@/api-types";
import type { AuditDone, AuditStreamState } from "@/hooks/useAuditStream";

const MAX_AGENT_EVENTS = 600;
const MAX_PROBE_EVENTS = 4000;
const TICK_MS = 80;
const MIN_DURATION_MS = 8_000;
const MAX_DURATION_MS = 45_000;
const DEFAULT_DURATION_MS = 30_000;

export const REPLAY_SPEEDS = [0.5, 1, 2, 4] as const;

interface Frame {
  at: number;
  seq: number;
  kind: StreamEvent["kind"];
  data: AgentEvent | ProbeEvent;
}

interface Timeline {
  frames: Frame[];
  /** Milliseconds at which each frame becomes visible. */
  ats: number[];
  durationMs: number;
}

function recordedDuration(audit: AuditRecord): number {
  const start = Date.parse(audit.started_at ?? "");
  const end = Date.parse(audit.completed_at ?? "");
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    return DEFAULT_DURATION_MS;
  }
  const elapsed = end - start;
  return Math.min(MAX_DURATION_MS, Math.max(MIN_DURATION_MS, elapsed));
}

function buildTimeline(replay: ReplayFile): Timeline {
  const events = replay.events ?? [];
  const durationMs = recordedDuration(replay.audit);
  const denominator = Math.max(1, events.length - 1);
  const frames = events.map((event, index) => ({
    at: Math.round((index / denominator) * durationMs),
    seq: event.seq,
    kind: event.kind,
    data: event.data,
  }));
  return { frames, ats: frames.map((frame) => frame.at), durationMs };
}

/** First index whose time is greater than `value`. */
function upperBound(values: number[], value: number): number {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (values[middle] <= value) low = middle + 1;
    else high = middle;
  }
  return low;
}

export interface ReplayPlayback extends AuditStreamState {
  playing: boolean;
  /** 0–1 of the recorded wall-clock window. */
  progress: number;
  positionMs: number;
  durationMs: number;
  speed: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  restart: () => void;
  seek: (fraction: number) => void;
  setSpeed: (speed: number) => void;
  skipToEnd: () => void;
}

export function useReplayPlayback(
  replay: ReplayFile | null,
  options: { autoplay?: boolean; initialSpeed?: number } = {},
): ReplayPlayback {
  const { autoplay = true, initialSpeed = 1 } = options;
  const timeline = React.useMemo(
    () => (replay ? buildTimeline(replay) : null),
    [replay],
  );

  const [positionMs, setPositionMs] = React.useState(0);
  const [playing, setPlaying] = React.useState(false);
  const [speed, setSpeed] = React.useState(initialSpeed);
  const positionRef = React.useRef(0);

  const durationMs = timeline?.durationMs ?? 0;
  const replayId = replay?.id ?? null;

  const moveTo = React.useCallback((next: number) => {
    const bounded = Math.max(0, Math.min(durationMs, next));
    positionRef.current = bounded;
    setPositionMs(bounded);
    return bounded;
  }, [durationMs]);

  React.useEffect(() => {
    positionRef.current = 0;
    setPositionMs(0);
    setSpeed(initialSpeed);
    setPlaying(Boolean(replayId && autoplay));
  }, [replayId, autoplay, initialSpeed]);

  React.useEffect(() => {
    if (!replay || !timeline || !playing) return;
    const timer = setInterval(() => {
      const next = positionRef.current + TICK_MS * speed;
      const reached = moveTo(next);
      if (reached >= timeline.durationMs) setPlaying(false);
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [replay, timeline, playing, speed, moveTo]);

  const revealed = timeline ? upperBound(timeline.ats, positionMs) : 0;

  const visible = React.useMemo(() => {
    if (!timeline) {
      return {
        agentEvents: [] as AgentEvent[],
        probeEvents: [] as ProbeEvent[],
        probeCount: 0,
      };
    }
    const agents: AgentEvent[] = [];
    const probes: ProbeEvent[] = [];
    let probeCount = 0;
    for (let index = 0; index < revealed; index += 1) {
      const frame = timeline.frames[index];
      if (frame.kind === "agent") {
        agents.push(frame.data as AgentEvent);
      } else {
        probeCount += 1;
        probes.push(frame.data as ProbeEvent);
      }
    }
    return {
      agentEvents:
        agents.length > MAX_AGENT_EVENTS
          ? agents.slice(agents.length - MAX_AGENT_EVENTS)
          : agents,
      probeEvents:
        probes.length > MAX_PROBE_EVENTS
          ? probes.slice(probes.length - MAX_PROBE_EVENTS)
          : probes,
      probeCount,
    };
  }, [timeline, revealed]);

  const finished = Boolean(timeline) && positionMs >= durationMs && durationMs > 0;
  const lastFrame = revealed > 0 ? timeline?.frames[revealed - 1] : undefined;
  const done: AuditDone | null =
    finished && replay
      ? {
          audit_id: replay.audit.id,
          status: "completed",
          error: null,
          last_seq: lastFrame?.seq ?? 0,
        }
      : null;

  const play = React.useCallback(() => {
    if (!timeline) return;
    if (positionRef.current >= timeline.durationMs) moveTo(0);
    setPlaying(true);
  }, [timeline, moveTo]);

  const pause = React.useCallback(() => setPlaying(false), []);
  const toggle = React.useCallback(() => {
    if (playing) pause();
    else play();
  }, [playing, pause, play]);

  const restart = React.useCallback(() => {
    moveTo(0);
    setPlaying(true);
  }, [moveTo]);

  const seek = React.useCallback(
    (fraction: number) => {
      if (!timeline) return;
      const bounded = Math.max(0, Math.min(1, fraction));
      moveTo(bounded * timeline.durationMs);
      if (bounded >= 1) setPlaying(false);
    },
    [timeline, moveTo],
  );

  const skipToEnd = React.useCallback(() => {
    if (!timeline) return;
    moveTo(timeline.durationMs);
    setPlaying(false);
  }, [timeline, moveTo]);

  return {
    status: !replay ? "connecting" : finished ? "done" : "open",
    agentEvents: visible.agentEvents,
    probeEvents: visible.probeEvents,
    probeCount: visible.probeCount,
    lastEventId: lastFrame?.seq ?? 0,
    reconnects: 0,
    error: null,
    done,
    playing,
    progress: durationMs > 0 ? Math.min(1, positionMs / durationMs) : 0,
    positionMs,
    durationMs,
    speed,
    play,
    pause,
    toggle,
    restart,
    seek,
    setSpeed,
    skipToEnd,
  };
}
