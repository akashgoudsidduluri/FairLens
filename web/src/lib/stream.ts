import type { AgentEvent, ProbeEvent, StreamEvent } from "@/api-types";
export type StreamFrame =
  | { seq: number; kind: "agent"; data: AgentEvent }
  | { seq: number; kind: "probe"; data: ProbeEvent };

/**
 * Defensive SSE frame parser.
 *
 * The service sends `{seq, kind, data}`. A malformed frame is dropped rather
 * than crashing the arena; the stream keeps its last good state.
 */
export function parseStreamData(raw: string, expected: "agent" | "probe"): StreamFrame | null {
  if (!raw) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;
  const seq = value.seq;
  const kind = value.kind;
  if (typeof seq !== "number" || !Number.isFinite(seq)) return null;
  if (kind !== expected) return null;
  const data = value.data;
  if (!isRecord(data)) return null;
  if (expected === "agent" && typeof data.agent !== "string") return null;
  if (expected === "probe" && typeof data.probe_id !== "string") return null;
  if (expected === "agent") {
    return { seq, kind: "agent", data: data as unknown as AgentEvent };
  }
  return { seq, kind: "probe", data: data as unknown as ProbeEvent };
}

/** Narrow a raw StreamEvent generated from OpenAPI. */
export function asStreamEvent(value: StreamEvent): StreamFrame {
  return value.kind === "probe"
    ? { seq: value.seq, kind: "probe", data: value.data as ProbeEvent }
    : { seq: value.seq, kind: "agent", data: value.data as AgentEvent };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export const PROBE_LABELS: Record<string, string> = {
  gender: "gender",
  age_band: "age band",
  pincode_group: "region group",
  name_group: "name group",
  urban_rural: "urban / rural",
  intersectional: "combined attributes",
  income: "income",
  credit_score: "credit score",
  employment_years: "employment years",
  loan_amount: "loan amount",
};

export function probeLabel(field: string): string {
  return PROBE_LABELS[field] ?? field.replaceAll("_", " ");
}

export const DECISION_LABEL = {
  approved: "approved",
  rejected: "rejected",
} as const;

/** Plain-language field names for the twin cards. */
export const FIELD_LABELS: Record<string, string> = {
  id: "applicant id",
  gender: "gender",
  age_band: "age band",
  urban_rural: "location",
  pincode_group: "region group",
  name_group: "name group",
  income: "annual income",
  credit_score: "credit score",
  employment_years: "employment years",
  loan_amount: "loan amount",
  age: "age",
  pincode: "pincode",
  name: "name",
};

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field.replaceAll("_", " ");
}
