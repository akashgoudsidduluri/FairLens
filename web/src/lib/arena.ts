import type { AgentEvent, ProbeEvent } from "@/api-types";

/** One pair can appear in more than one SSE connection after a resume. */
export function pairKey(event: ProbeEvent): string {
  return `${event.phase}:${event.probe_id}:${event.pair_index}`;
}

export function isFlip(event: ProbeEvent): boolean {
  return event.original_approved !== event.twin_approved;
}

/** Hard cap on the archived history kept for one probe. */
export const MAX_ARCHIVED_POINTS = 240;

/**
 * Thin a series to at most `maxPoints` while keeping the first and last point.
 *
 * Both edges matter: the first point anchors where an attribute started, and
 * the last is the running estimate a reader is looking at now.
 */
function thinPoints<T>(points: T[], maxPoints: number): T[] {
  if (maxPoints <= 0) return [];
  if (points.length <= maxPoints) return [...points];
  if (maxPoints === 1) return [points[points.length - 1]];
  const step = (points.length - 1) / (maxPoints - 1);
  return Array.from(
    { length: maxPoints },
    (_, index) => points[Math.round(index * step)],
  );
}

/**
 * Append one event to a probe's archive and trim it back to the hard cap.
 *
 * The archive outlives the capped render buffer, so it must stay bounded
 * without dropping the first or latest observation for the attribute.
 */
export function appendArchivedPoint(
  points: ProbeEvent[],
  event: ProbeEvent,
  maxPoints = MAX_ARCHIVED_POINTS,
): ProbeEvent[] {
  const next = [...points, event];
  return next.length <= maxPoints ? next : thinPoints(next, maxPoints);
}

export interface EvidencePoint {
  n: number;
  net: number;
  band: [number, number];
}

/**
 * The running interval is per-probe: `n_running` starts at zero for each
 * attribute. Chart one probe at a time, so the band narrows monotonically
 * instead of jumping back to zero when a new attribute starts.
 */
export function evidenceSeries(
  events: ProbeEvent[],
  maxPoints = 120,
  probeId?: string,
): EvidencePoint[] {
  if (events.length === 0) return [];
  const target = probeId ?? events[events.length - 1].probe_id;
  const points = events.filter((event) => event.probe_id === target);
  if (points.length === 0) return [];
  return thinPoints(points, maxPoints).map((event) => ({
    n: event.n_running,
    net: event.net_flip_rate_running * 100,
    band: [event.ci_low_running * 100, event.ci_high_running * 100],
  }));
}

export interface ProbeSummary {
  probeId: string;
  changedField: string;
  phase: ProbeEvent["phase"];
  n: number;
  net: number;
}

export function probeSummary(event: ProbeEvent): ProbeSummary {
  return {
    probeId: event.probe_id,
    changedField: event.changed_field,
    phase: event.phase,
    n: event.n_running,
    net: event.net_flip_rate_running,
  };
}

/**
 * Attributes, not probe ids, are what a reader compares.
 *
 * One attribute runs as several probes (comparison group A→B, then B→A, then a
 * matched retest), so the strip collapses them into one row per attribute and
 * shows the latest probe for it. Otherwise the row repeats four times.
 */
export interface EvidenceGroup {
  key: string;
  latest: ProbeSummary;
  count: number;
}

export function evidenceGroupKey(summary: ProbeSummary): string {
  return summary.phase === "intersectional"
    ? "intersectional"
    : summary.changedField;
}

export function evidenceGroups(summaries: ProbeSummary[]): EvidenceGroup[] {
  const groups = new Map<string, EvidenceGroup>();
  for (const summary of summaries) {
    const key = evidenceGroupKey(summary);
    const existing = groups.get(key);
    if (existing) {
      existing.latest = summary;
      existing.count += 1;
    } else {
      groups.set(key, { key, latest: summary, count: 1 });
    }
  }
  return [...groups.values()];
}

export interface EarlyStop {
  attribute: string;
  n: number;
  requestedN: number;
  reason: string;
  message: string;
}

const STOP_COPY: Record<string, string> = {
  stop_material_harm:
    "the live interval is already above the materiality line, so enough evidence of material harm has accumulated",
  stop_no_material_harm:
    "the live interval is entirely below the materiality line, so more pairs are unlikely to change the call",
  max_pairs: "the pre-registered maximum number of pairs was reached",
};

export function stopReasonCopy(reason: string): string {
  return STOP_COPY[reason] ?? reason.replaceAll("_", " ");
}

/** The most recent sequential-stopping event, if any. */
export function latestEarlyStop(events: AgentEvent[]): EarlyStop | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    const payload = event.payload ?? {};
    const reason = payload.stop_reason;
    if (typeof reason !== "string" || !reason || reason === "continue") continue;
    return {
      attribute: typeof payload.attribute === "string" ? payload.attribute : "",
      n: Number(payload.n ?? 0),
      requestedN: Number(payload.requested_n ?? 0),
      reason,
      message: stopReasonCopy(reason),
    };
  }
  return null;
}

export const LANE_IDS = ["prober", "statistician", "skeptic", "reporter"] as const;
export type LaneId = (typeof LANE_IDS)[number];

const LANE_OF_AGENT: Record<string, LaneId> = {
  planner: "prober",
  prober: "prober",
  statistician: "statistician",
  skeptic: "skeptic",
  reporter: "reporter",
  impact: "reporter",
};

export function laneForAgent(agent: string): LaneId {
  return LANE_OF_AGENT[agent] ?? "prober";
}

export interface LaneState {
  id: LaneId;
  count: number;
  latest: AgentEvent | null;
}

export function laneStates(events: AgentEvent[]): LaneState[] {
  return LANE_IDS.map((id) => {
    const received = events.filter((event) => laneForAgent(event.agent) === id);
    return {
      id,
      count: received.length,
      latest: received.length > 0 ? received[received.length - 1] : null,
    };
  });
}

/** Format a fraction as a signed percentage with two decimals. */
export function signedPercent(value: number): string {
  const percent = value * 100;
  return `${percent >= 0 ? "+" : ""}${percent.toFixed(2)}%`;
}

export function countNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function compactNumber(value: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: value >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

/** Human label for the audit record's target reference. */
export function targetLabel(
  target?: string | null,
  modelId?: number | null,
): string {
  if (!target) return modelId ? `Validation model ${modelId}` : "Audit target";
  if (target.startsWith("sandbox:")) {
    return `Validation model ${target.split(":")[1] ?? ""}`.trim();
  }
  if (target === "llm:screener") return "LLM screener";
  if (target.startsWith("inline:")) return "Connected endpoint";
  if (target.includes("adult")) return "Adult Income";
  if (target.includes("credit")) return "UCI Credit Default";
  return target;
}
