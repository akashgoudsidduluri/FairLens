import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentEvent, ProbeEvent } from "@/api-types";
import { useAuditStream } from "@/hooks/useAuditStream";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    const list = this.listeners.get(type) ?? [];
    list.push(listener as (event: MessageEvent<string>) => void);
    this.listeners.set(type, list);
  }

  close() {
    this.closed = true;
  }

  open() {
    this.onopen?.();
  }

  fail() {
    this.onerror?.();
  }

  emit(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent<string>;
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }

  emitRaw(type: string, data: string) {
    const event = { data } as MessageEvent<string>;
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

const agent = (agentName: string): AgentEvent => ({
  agent: agentName,
  message: "working",
  payload: {},
});

function probe(index: number, b = 1): ProbeEvent {
  return {
    probe_id: "single-gender-male",
    phase: "single_attribute",
    pair_index: index,
    changed_field: "gender",
    original: { id: `o${index}`, gender: "male" },
    twin: { id: `t${index}`, gender: "female" },
    original_approved: true,
    twin_approved: false,
    b_running: b,
    c_running: 0,
    n_running: index + 1,
    net_flip_rate_running: b / (index + 1),
    ci_low_running: 0,
    ci_high_running: 1,
    ci_method: "normal_approximation",
  };
}

const factory = (url: string) => new FakeEventSource(url) as unknown as EventSource;

describe("useAuditStream", () => {
  it("dedupes by sequence and keeps agent and probe frames", async () => {
    FakeEventSource.instances = [];
    const { result } = renderHook(() =>
      useAuditStream("abc", { batchMs: 0, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.instances[0].url).toBe("/api/audits/abc/events");

    act(() => {
      FakeEventSource.instances[0].emit("agent", { seq: 1, kind: "agent", data: agent("prober") });
      FakeEventSource.instances[0].emit("agent", { seq: 1, kind: "agent", data: agent("prober") });
      FakeEventSource.instances[0].emit("probe", { seq: 2, kind: "probe", data: probe(0) });
    });

    expect(result.current.agentEvents).toHaveLength(1);
    expect(result.current.probeEvents).toHaveLength(1);
    expect(result.current.probeCount).toBe(1);
    expect(result.current.lastEventId).toBe(2);
  });

  it("buffers probe frames into batches", async () => {
    FakeEventSource.instances = [];
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useAuditStream("abc", { batchMs: 100, eventSourceFactory: factory }),
    );
    await vi.advanceTimersByTimeAsync(0);
    act(() => {
      FakeEventSource.instances[0].emit("probe", { seq: 1, kind: "probe", data: probe(0) });
      FakeEventSource.instances[0].emit("probe", { seq: 2, kind: "probe", data: probe(1) });
    });
    expect(result.current.probeEvents).toHaveLength(0);
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(result.current.probeEvents).toHaveLength(2);
    expect(result.current.probeCount).toBe(2);
  });

  it("reconnects from the last event id after a dropped connection", async () => {
    FakeEventSource.instances = [];
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useAuditStream("abc", { batchMs: 0, eventSourceFactory: factory }),
    );
    await vi.advanceTimersByTimeAsync(0);
    const first = FakeEventSource.instances[0];
    act(() => {
      first.open();
      first.emit("agent", { seq: 1, kind: "agent", data: agent("prober") });
      first.emit("probe", { seq: 2, kind: "probe", data: probe(0) });
    });
    expect(result.current.status).toBe("open");

    act(() => first.fail());
    expect(first.closed).toBe(true);
    expect(result.current.status).toBe("reconnecting");
    expect(result.current.reconnects).toBe(1);

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].url).toBe(
      "/api/audits/abc/events?last_event_id=2",
    );
    expect(result.current.lastEventId).toBe(2);
  });

  it("stops on done and does not reconnect", async () => {
    FakeEventSource.instances = [];
    vi.useFakeTimers();
    const { result } = renderHook(() =>
      useAuditStream("abc", { batchMs: 0, eventSourceFactory: factory }),
    );
    await vi.advanceTimersByTimeAsync(0);
    const source = FakeEventSource.instances[0];

    act(() => {
      source.emitRaw(
        "done",
        JSON.stringify({ audit_id: "abc", status: "completed", last_seq: 2 }),
      );
    });
    expect(result.current.status).toBe("done");
    expect(result.current.done?.status).toBe("completed");
    expect(source.closed).toBe(true);

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
