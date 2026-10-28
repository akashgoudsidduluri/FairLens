import { describe, expect, it } from "vitest";

import {
  MAX_ARCHIVED_POINTS,
  appendArchivedPoint,
  evidenceGroups,
  evidenceSeries,
  isFlip,
  laneForAgent,
  laneStates,
  latestEarlyStop,
  pairKey,
  probeSummary,
  signedPercent,
  stopReasonCopy,
  targetLabel,
} from "@/lib/arena";
import { makeAgent, makeProbe } from "@/test/fixtures";

describe("arena helpers", () => {
  it("identifies flips and builds stable pair keys", () => {
    expect(isFlip(makeProbe())).toBe(true);
    expect(isFlip(makeProbe({ twin_approved: true }))).toBe(false);
    expect(pairKey(makeProbe())).toBe("single_attribute:single-gender-female:0");
  });

  it("charts only the latest probe so the band narrows monotonically", () => {
    const events = [
      makeProbe({ pair_index: 0, b_running: 0, c_running: 0, n_running: 1, net_flip_rate_running: 0 }),
      makeProbe({ pair_index: 1, b_running: 1, c_running: 0, n_running: 2, net_flip_rate_running: 0.5 }),
      makeProbe({
        probe_id: "single-pincode_group-female",
        pair_index: 0,
        b_running: 0,
        c_running: 0,
        n_running: 1,
        net_flip_rate_running: 0,
        changed_field: "pincode_group",
      }),
    ];
    const series = evidenceSeries(events);
    expect(series).toHaveLength(1);
    expect(series[0]).toEqual({ n: 1, net: 0, band: [0, 10] });
  });

  it("downsamples long series while keeping the first and last points", () => {
    const events = Array.from({ length: 500 }, (_, index) =>
      makeProbe({
        pair_index: index,
        b_running: index,
        c_running: 0,
        n_running: index + 1,
        net_flip_rate_running: 1,
      }),
    );
    const series = evidenceSeries(events, 50);
    expect(series.length).toBeLessThanOrEqual(50);
    expect(series[0].n).toBe(1);
    expect(series[series.length - 1].n).toBe(500);
    expect(
      series.every((point, index) => index === 0 || point.n > series[index - 1].n),
    ).toBe(true);
  });

  it("hard-caps an archived probe history without losing either edge", () => {
    let points: Parameters<typeof appendArchivedPoint>[0] = [];
    const total = MAX_ARCHIVED_POINTS * 3;
    for (let index = 0; index < total; index += 1) {
      points = appendArchivedPoint(
        points,
        makeProbe({ pair_index: index, n_running: index + 1 }),
      );
    }
    expect(points.length).toBe(MAX_ARCHIVED_POINTS);
    expect(points[0].pair_index).toBe(0);
    expect(points[points.length - 1].pair_index).toBe(total - 1);
  });

  it("can chart a chosen probe and summarize every attribute seen", () => {
    const events = [
      makeProbe({
        pair_index: 0,
        b_running: 1,
        c_running: 0,
        n_running: 1,
        net_flip_rate_running: 1,
      }),
      makeProbe({
        pair_index: 1,
        b_running: 2,
        c_running: 0,
        n_running: 2,
        net_flip_rate_running: 1,
      }),
      makeProbe({
        probe_id: "single-pincode_group-female",
        pair_index: 0,
        changed_field: "pincode_group",
        b_running: 0,
        c_running: 0,
        n_running: 1,
        net_flip_rate_running: 0,
      }),
    ];

    // The default still follows the newest probe…
    expect(evidenceSeries(events).at(-1)?.n).toBe(1);
    // …and a pinned probe keeps its own history.
    expect(evidenceSeries(events, 120, "single-gender-female").at(-1)).toEqual({
      n: 2,
      net: 100,
      band: [0, 10],
    });

    expect(probeSummary(events[2])).toEqual({
      probeId: "single-pincode_group-female",
      changedField: "pincode_group",
      phase: "single_attribute",
      n: 1,
      net: 0,
    });

    // Several probes for one attribute collapse into one comparable row.
    const groups = evidenceGroups([
      probeSummary(events[1]),
      probeSummary(events[2]),
      {
        probeId: "matched-gender-male",
        changedField: "gender",
        phase: "matched_retest",
        n: 900,
        net: 0.03,
      },
    ]);
    expect(groups.map((group) => group.key)).toEqual([
      "gender",
      "pincode_group",
    ]);
    expect(groups[0].count).toBe(2);
    expect(groups[0].latest.probeId).toBe("matched-gender-male");
  });

  it("collapses A→B, B→A and matched retests into one row per attribute", () => {
    const probes = [
      makeProbe({
        probe_id: "single-gender-female",
        phase: "single_attribute",
        changed_field: "gender",
      }),
      makeProbe({
        probe_id: "single-gender-male",
        phase: "single_attribute",
        changed_field: "gender",
      }),
      makeProbe({
        probe_id: "matched-gender-female",
        phase: "matched_retest",
        changed_field: "gender",
        n_running: 900,
      }),
      makeProbe({
        probe_id: "single-pincode_group-female",
        phase: "single_attribute",
        changed_field: "pincode_group",
      }),
    ];
    const groups = evidenceGroups(probes.map(probeSummary));

    expect(groups.map((group) => group.key)).toEqual(["gender", "pincode_group"]);
    expect(groups[0].count).toBe(3);
    expect(groups[0].latest.probeId).toBe("matched-gender-female");
    expect(groups[0].latest.n).toBe(900);
  });

  it("returns an empty series for an unknown probe id instead of throwing", () => {
    const events = [makeProbe()];
    expect(() => evidenceSeries(events, 120, "probe-that-does-not-exist")).not.toThrow();
    expect(evidenceSeries(events, 120, "probe-that-does-not-exist")).toEqual([]);
  });

  it("finds the latest sequential stop and ignores continue decisions", () => {
    const events = [
      makeAgent({ agent: "statistician", payload: { stop_reason: "continue", n: 800 } }),
      makeAgent({
        agent: "statistician",
        payload: {
          attribute: "gender",
          n: 1200,
          requested_n: 2000,
          stop_reason: "stop_material_harm",
        },
      }),
      makeAgent({ agent: "skeptic", payload: {} }),
    ];
    const stop = latestEarlyStop(events);
    expect(stop).toMatchObject({
      attribute: "gender",
      n: 1200,
      requestedN: 2000,
      reason: "stop_material_harm",
    });
    expect(stop?.message).toContain("above the materiality line");
    expect(latestEarlyStop([makeAgent({ payload: { stop_reason: "continue" } })])).toBeNull();
  });

  it("maps agent names onto the four lanes and counts their events", () => {
    expect(laneForAgent("planner")).toBe("prober");
    expect(laneForAgent("impact")).toBe("reporter");
    const lanes = laneStates([
      makeAgent({ agent: "planner", message: "plan" }),
      makeAgent({ agent: "impact", message: "impact" }),
      makeAgent({ agent: "statistician", message: "estimate" }),
    ]);
    expect(lanes.map((lane) => lane.id)).toEqual([
      "prober",
      "statistician",
      "skeptic",
      "reporter",
    ]);
    expect(lanes[0].latest?.message).toBe("plan");
    expect(lanes[2].latest).toBeNull();
    expect(lanes[3].latest?.message).toBe("impact");
  });

  it("uses plain language for early-stop reasons and targets", () => {
    expect(stopReasonCopy("stop_no_material_harm")).toContain("below the materiality");
    expect(stopReasonCopy("custom_reason")).toBe("custom reason");
    expect(targetLabel("sandbox:3", 3)).toBe("Validation model 3");
    expect(targetLabel("targets/real/adult-income.yaml", 2)).toBe("Adult Income");
    expect(targetLabel("targets/real/uci-credit-default.yaml", 1)).toBe(
      "UCI Credit Default",
    );
    expect(targetLabel("llm:screener", 1)).toBe("LLM screener");
    expect(targetLabel("inline:connected-endpoint", 1)).toBe("Connected endpoint");
  });

  it("formats signed percentages", () => {
    expect(signedPercent(0.0123)).toBe("+1.23%");
    expect(signedPercent(-0.02)).toBe("-2.00%");
  });
});
