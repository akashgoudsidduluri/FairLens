import type {
  AgentEvent,
  AuditReport,
  Finding,
  ImpactEstimate,
} from "@/api-types";
import { probeLabel } from "@/lib/stream";

/** One rule the Skeptic evaluated for a candidate finding. */
export interface SkepticCheck {
  name: string;
  passed: boolean;
  detail: string;
}

/** The latest Skeptic verdict for one finding, read from the agent stream. */
export interface SkepticReview {
  findingId: string;
  status: string;
  checks: SkepticCheck[];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function parseChecks(value: unknown): SkepticCheck[] {
  if (!Array.isArray(value)) return [];
  const checks: SkepticCheck[] = [];
  for (const item of value) {
    const raw = asRecord(item);
    if (!raw || typeof raw.name !== "string") continue;
    checks.push({
      name: raw.name,
      passed: raw.passed === true,
      detail: typeof raw.detail === "string" ? raw.detail : "",
    });
  }
  return checks;
}

/**
 * Read the Skeptic checks from the stream.
 *
 * The report persists the verdict as a status and a reason; the individual
 * checks only exist on the `skeptic` agent event. Keep the newest event for a
 * finding so a resumed stream cannot show a stale verdict.
 */
export function skepticReviews(
  events: AgentEvent[],
): Record<string, SkepticReview> {
  const reviews: Record<string, SkepticReview> = {};
  for (const event of events) {
    if (event.agent !== "skeptic") continue;
    const payload = asRecord(event.payload);
    if (!payload) continue;
    const findingId = payload.finding_id;
    if (typeof findingId !== "string") continue;
    const checks = parseChecks(payload.checks);
    if (checks.length === 0) continue;
    reviews[findingId] = {
      findingId,
      status: typeof payload.status === "string" ? payload.status : "",
      checks,
    };
  }
  return reviews;
}

const CHECK_LABELS: Record<string, string> = {
  min_sample_size: "sample size",
  significance_after_correction: "significance after correction",
  materiality: "materiality",
  symmetric_noise: "directional signal",
  income_matched_persistence: "income-matched re-test",
  confounding_check: "confounding check",
};

export function checkLabel(name: string): string {
  return CHECK_LABELS[name] ?? name.replaceAll("_", " ");
}

function upperFirst(value: string): string {
  return value.length > 0 ? value[0].toUpperCase() + value.slice(1) : value;
}

/** A short, human title for a finding card. */
export function findingTitle(finding: Finding): string {
  if (finding.kind === "intersectional") {
    const [gender, ageBand, location] = finding.target_group.split("|");
    return [upperFirst(gender ?? ""), ageBand ?? "", location ?? ""]
      .filter(Boolean)
      .join(" · ");
  }
  const field = finding.attribute_or_subgroup.split("=", 1)[0];
  return `${upperFirst(probeLabel(field))}: ${finding.target_group} vs ${finding.comparison_group}`;
}

export interface ReportCounts {
  kept: number;
  rejected: number;
  immaterial: number;
  candidate: number;
}

export function reportCounts(findings: Finding[]): ReportCounts {
  const counts: ReportCounts = {
    kept: 0,
    rejected: 0,
    immaterial: 0,
    candidate: 0,
  };
  for (const finding of findings) {
    counts[finding.status] += 1;
  }
  return counts;
}

/** Kept findings first, then rejected/immaterial, preserving report order. */
export function orderedFindings(findings: Finding[]): Finding[] {
  const rank: Record<Finding["status"], number> = {
    kept: 0,
    immaterial: 1,
    rejected: 2,
    candidate: 3,
  };
  return [...findings].sort((left, right) => rank[left.status] - rank[right.status]);
}

export interface HeatmapCell {
  key: string;
  gender: string;
  ageBand: string;
  urbanRural: string;
  net: number;
  n: number;
  pAdjusted: number | null;
  status: Finding["status"] | null;
}

export interface HeatmapLayout {
  genders: string[];
  rows: Array<{
    ageBand: string;
    urbanRural: string;
    cells: Record<string, HeatmapCell>;
  }>;
}

const AGE_ORDER = ["<35", "35-44", "45+"];

function ageRank(ageBand: string): number {
  const index = AGE_ORDER.indexOf(ageBand);
  return index === -1 ? AGE_ORDER.length : index;
}

/**
 * The intersectional grid, with the Skeptic status joined from findings.
 *
 * The observational cells cover every scanned cell, including controls that
 * produced no candidate. That makes the empty cells meaningful: they show the
 * scanner actually looked there.
 */
export function heatmapLayout(report: AuditReport): HeatmapLayout {
  const findings = report.findings ?? [];
  const statusByGroup = new Map<string, Finding["status"]>();
  for (const finding of findings) {
    if (finding.kind === "intersectional") {
      statusByGroup.set(finding.target_group, finding.status);
    }
  }

  const cells: HeatmapCell[] = [];
  const observational = asRecord(report.observational);
  const rawCells = observational?.intersectional_cells;
  if (Array.isArray(rawCells)) {
    for (const item of rawCells) {
      const raw = asRecord(item);
      if (!raw) continue;
      const gender = typeof raw.target_gender === "string" ? raw.target_gender : "";
      const ageBand = typeof raw.age_band === "string" ? raw.age_band : "";
      const urbanRural =
        typeof raw.urban_rural === "string" ? raw.urban_rural : "";
      if (!gender || !ageBand || !urbanRural) continue;
      const key = `${gender}|${ageBand}|${urbanRural}`;
      cells.push({
        key,
        gender,
        ageBand,
        urbanRural,
        net: Number(raw.net_flip_rate ?? 0),
        n: Number(raw.n ?? 0),
        pAdjusted:
          typeof raw.p_adjusted === "number" ? raw.p_adjusted : null,
        status: statusByGroup.get(key) ?? null,
      });
    }
  }

  // A report from an older adapter may have findings but no cell grid.
  if (cells.length === 0) {
    for (const finding of findings) {
      if (finding.kind !== "intersectional") continue;
      const [gender, ageBand, urbanRural] = finding.target_group.split("|");
      if (!gender || !ageBand || !urbanRural) continue;
      cells.push({
        key: finding.target_group,
        gender,
        ageBand,
        urbanRural,
        net: finding.evidence.net_flip_rate,
        n: finding.evidence.n,
        pAdjusted: finding.evidence.p_adjusted,
        status: finding.status,
      });
    }
  }

  const genders = [...new Set(cells.map((cell) => cell.gender))].sort();
  const rowKeys = new Map<string, { ageBand: string; urbanRural: string }>();
  for (const cell of cells) {
    const key = `${cell.ageBand}|${cell.urbanRural}`;
    if (!rowKeys.has(key)) {
      rowKeys.set(key, {
        ageBand: cell.ageBand,
        urbanRural: cell.urbanRural,
      });
    }
  }
  const rows = [...rowKeys.entries()]
    .sort(([left], [right]) => {
      const [leftAge, leftLocation] = left.split("|");
      const [rightAge, rightLocation] = right.split("|");
      return (
        ageRank(leftAge) - ageRank(rightAge) ||
        leftLocation.localeCompare(rightLocation)
      );
    })
    .map(([key, value]) => {
      const rowCells: Record<string, HeatmapCell> = {};
      for (const cell of cells) {
        if (`${cell.ageBand}|${cell.urbanRural}` === key) {
          rowCells[cell.gender] = cell;
        }
      }
      return { ...value, cells: rowCells };
    });

  return { genders, rows };
}

export function impactSorted(impact: ImpactEstimate[]): ImpactEstimate[] {
  return [...impact].sort((left, right) => right.per_10k - left.per_10k);
}

export function narrativePassed(report: AuditReport): boolean {
  return report.number_check_result?.passed === true;
}

export function narrativeSource(report: AuditReport): string {
  const source = report.number_check_result?.source;
  return typeof source === "string" ? source : "unknown";
}
