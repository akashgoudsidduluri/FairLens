import { describe, expect, it } from "vitest";

import type { AgentEvent, ProbeEvent } from "@/api-types";
import { parseStreamData, probeLabel } from "@/lib/stream";

const agent: AgentEvent = {
  agent: "prober",
  message: "sampling",
  payload: {},
};

const probe: ProbeEvent = {
  probe_id: "single-gender-male",
  phase: "single_attribute",
  pair_index: 0,
  changed_field: "gender",
  original: { id: "a", gender: "male" },
  twin: { id: "b", gender: "female" },
  original_approved: true,
  twin_approved: false,
  b_running: 1,
  c_running: 0,
  n_running: 1,
  net_flip_rate_running: 1,
  ci_low_running: 0.5,
  ci_high_running: 1,
  ci_method: "normal_approximation",
};

describe("SSE frame parsing", () => {
  it("parses a valid agent frame", () => {
    const frame = parseStreamData(
      JSON.stringify({ seq: 1, kind: "agent", data: agent }),
      "agent",
    );
    expect(frame?.seq).toBe(1);
    expect(frame?.data).toMatchObject({ agent: "prober" });
  });

  it("parses a valid probe frame", () => {
    const frame = parseStreamData(
      JSON.stringify({ seq: 2, kind: "probe", data: probe }),
      "probe",
    );
    expect(frame?.kind).toBe("probe");
  });

  it("drops malformed, mistyped, and kind-mismatched frames", () => {
    expect(parseStreamData("{", "agent")).toBeNull();
    expect(parseStreamData(JSON.stringify({ seq: 1, kind: "probe", data: probe }), "agent")).toBeNull();
    expect(parseStreamData(JSON.stringify({ seq: "1", kind: "agent", data: agent }), "agent")).toBeNull();
    expect(parseStreamData(JSON.stringify({ seq: 1, kind: "agent", data: {} }), "agent")).toBeNull();
  });

  it("uses plain language for probe fields", () => {
    expect(probeLabel("gender")).toBe("gender");
    expect(probeLabel("pincode_group")).toBe("region group");
    expect(probeLabel("unknown_field")).toBe("unknown field");
  });
});
