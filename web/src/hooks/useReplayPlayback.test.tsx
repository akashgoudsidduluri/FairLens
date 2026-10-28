import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuditRecord, ReplayFile, StreamEvent } from "@/api-types";
import { useReplayPlayback } from "@/hooks/useReplayPlayback";
import { makeAgent, makeProbe } from "@/test/fixtures";

function replay(): ReplayFile {
  const audit: AuditRecord = {
    id: "source-audit",
    status: "completed",
    model_id: 2,
    target: "sandbox:2",
    api_url: "http://127.0.0.1:8010",
    seed: 42,
    include_mitigation: false,
    include_narrative: false,
    created_at: "2026-01-01T00:00:00Z",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T00:00:10Z",
    result: {
      model_id: 2,
      config: {},
      findings: [],
      narrative: "",
    },
  };
  const events: StreamEvent[] = [
    { seq: 1, kind: "agent", data: makeAgent({ message: "plan" }) },
    { seq: 2, kind: "probe", data: makeProbe({ pair_index: 0 }) },
    { seq: 3, kind: "agent", data: makeAgent({ message: "testing" }) },
    { seq: 4, kind: "probe", data: makeProbe({ pair_index: 1 }) },
    { seq: 5, kind: "probe", data: makeProbe({ pair_index: 2 }) },
  ];
  return {
    version: 1,
    id: "sandbox-2-seed-42",
    label: "Validation model 2",
    recorded_at: "2026-01-01T00:00:10Z",
    source_audit_id: "source-audit",
    audit,
    events,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("useReplayPlayback", () => {
  it("reveals frames over the recorded duration and can pause, seek, and restart", async () => {
    vi.useFakeTimers();
    const recording = replay();
    const { result } = renderHook(() => useReplayPlayback(recording));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(result.current.durationMs).toBe(10_000);
    expect(result.current.playing).toBe(true);
    expect(result.current.status).toBe("open");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(result.current.progress).toBeGreaterThan(0.4);
    expect(result.current.progress).toBeLessThan(0.6);
    expect(result.current.probeCount).toBeGreaterThan(0);
    expect(result.current.probeCount).toBeLessThan(3);
    expect(result.current.lastEventId).toBeGreaterThan(0);

    act(() => result.current.pause());
    const pausedAt = result.current.positionMs;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });
    expect(result.current.positionMs).toBe(pausedAt);
    expect(result.current.playing).toBe(false);

    act(() => result.current.seek(1));
    expect(result.current.progress).toBe(1);
    expect(result.current.probeCount).toBe(3);
    expect(result.current.agentEvents).toHaveLength(2);
    expect(result.current.status).toBe("done");
    expect(result.current.done?.audit_id).toBe("source-audit");

    act(() => result.current.restart());
    expect(result.current.positionMs).toBe(0);
    expect(result.current.playing).toBe(true);
    expect(result.current.status).toBe("open");
  });

  it("plays faster at higher speeds without skipping frames", async () => {
    vi.useFakeTimers();
    const recording = replay();
    const { result } = renderHook(() => useReplayPlayback(recording));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => result.current.setSpeed(4));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(result.current.positionMs).toBeGreaterThanOrEqual(3_800);
    expect(result.current.positionMs).toBeLessThanOrEqual(4_100);
  });

  it("stays empty while the recording is still loading", () => {
    const { result } = renderHook(() => useReplayPlayback(null));
    expect(result.current.status).toBe("connecting");
    expect(result.current.probeCount).toBe(0);
    expect(result.current.playing).toBe(false);
  });
});
