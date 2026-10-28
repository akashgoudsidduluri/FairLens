import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useProbeArchive } from "@/hooks/useProbeArchive";
import { MAX_ARCHIVED_POINTS } from "@/lib/arena";
import { makeProbe } from "@/test/fixtures";

describe("useProbeArchive", () => {
  it("keeps one history per probe and ignores replayed pairs", () => {
    const gender = makeProbe({ pair_index: 0 });
    const { result, rerender } = renderHook(
      ({ events, auditId }) => useProbeArchive(events, auditId),
      { initialProps: { events: [gender], auditId: "audit-1" } },
    );

    expect(result.current.order).toEqual(["single-gender-female"]);
    expect(result.current.byId["single-gender-female"]).toHaveLength(1);

    // A resume can replay the same pair on a second SSE connection.
    rerender({ events: [gender, gender], auditId: "audit-1" });
    expect(result.current.byId["single-gender-female"]).toHaveLength(1);
  });

  it("keeps an earlier attribute after its events leave the render buffer", () => {
    const gender = makeProbe({
      pair_index: 1999,
      b_running: 40,
      c_running: 0,
      n_running: 2000,
      net_flip_rate_running: 0.02,
    });
    const pincode = makeProbe({
      probe_id: "single-pincode_group-female",
      pair_index: 0,
      changed_field: "pincode_group",
    });
    const { result, rerender } = renderHook(
      ({ events, auditId }) => useProbeArchive(events, auditId),
      { initialProps: { events: [gender], auditId: "audit-1" } },
    );

    // The capped stream now holds only the newest attribute's frames.
    rerender({ events: [pincode], auditId: "audit-1" });

    expect(result.current.order).toEqual([
      "single-gender-female",
      "single-pincode_group-female",
    ]);
    expect(result.current.byId["single-gender-female"]).toHaveLength(1);
    expect(result.current.byId["single-gender-female"][0].n_running).toBe(2000);
    expect(result.current.byId["single-pincode_group-female"]).toHaveLength(1);
  });

  it("caps a probe history while keeping the first and last point", () => {
    const total = MAX_ARCHIVED_POINTS * 3;
    const events = Array.from({ length: total }, (_, index) =>
      makeProbe({ pair_index: index, n_running: index + 1 }),
    );
    const { result } = renderHook(() => useProbeArchive(events, "audit-1"));

    const points = result.current.byId["single-gender-female"];
    expect(points.length).toBe(MAX_ARCHIVED_POINTS);
    expect(points[0].pair_index).toBe(0);
    expect(points[points.length - 1].pair_index).toBe(total - 1);
  });

  it("starts a fresh archive when the audit changes", () => {
    const gender = makeProbe({ pair_index: 0 });
    const { result, rerender } = renderHook(
      ({ events, auditId }) => useProbeArchive(events, auditId),
      { initialProps: { events: [gender], auditId: "audit-1" } },
    );
    expect(result.current.order).toHaveLength(1);

    rerender({ events: [], auditId: "audit-2" });
    expect(result.current).toEqual({ order: [], byId: {} });
  });
});
