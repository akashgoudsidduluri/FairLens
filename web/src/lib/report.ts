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
  if (finding.kind === "generalized" && finding.treatment) {
    const level = finding.treatment_level ?? finding.target_group;
    const context = Object.entries(finding.context ?? {})
      .map(([key, value]) => `${probeLabel(key)}=${value}`)
      .join(", ");
    const base = `${upperFirst(probeLabel(finding.treatment))}: ${level} vs ${finding.comparison_group}`;
    return context ? `${base} · ${context}` : base;
  }
  if (finding.kind === "intersectional") {
    const [gender, ageBand, location] = finding.target_group.split("|");
    return [upperFirst(gender ?? ""), ageBand ?? "", location ?? ""]
      .filter(Boolean)
      .join(" · ");
  }
  const field = finding.attribute_or_subgroup.split("=", 1)[0];
  return `${upperFirst(probeLabel(field))}: ${finding.target_group} vs ${finding.comparison_group}`;
}

/** One generalized cell, indexed by the two chosen context axes. */
export interface GeneralizedCell {
  key: string;
  row: string;
  column: string;
  net: number;
  n: number;
  pAdjusted: number | null;
  status: Finding["status"] | null;
  depth: number;
  context: Record<string, string>;
  cellId: string;
}

export interface GeneralizedHeatmap {
  treatment: string;
  level: string;
  rowAttribute: string;
  columnAttribute: string;
  rowValues: string[];
  columnValues: string[];
  cells: Record<string, GeneralizedCell>;
  /** Cells with the same axes but a context the grid cannot show. */
  hidden: number;
}

export interface SearchDimensions {
  treatments: string[];
  levelsByTreatment: Record<string, string[]>;
  contextAttributes: string[];
}

export const ALL_CONTEXTS = "*";

function discoveryRows(report: AuditReport): Record<string, unknown>[] {
  const observational = asRecord(report.observational);
  const search = asRecord(observational?.search);
  const rows = search?.discovery_results;
  if (!Array.isArray(rows)) return [];
  return rows
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null);
}

function contextOf(row: Record<string, unknown>): Record<string, string> {
  const raw = asRecord(row.context);
  const context: Record<string, string> = {};
  if (!raw) return context;
  for (const [key, value] of Object.entries(raw)) {
    context[key] = String(value);
  }
  return context;
}

/**
 * The selectable axes of the generalized search.
 *
 * Treatments and levels come from the discovery rows, so the UI never invents
 * a treatment the audit did not run. Context attributes are ordered by how many
 * cells use them, which makes the two most useful axes the defaults.
 */
export function searchDimensions(report: AuditReport): SearchDimensions {
  const levels = new Map<string, Set<string>>();
  const attributeCounts = new Map<string, number>();
  for (const row of discoveryRows(report)) {
    const treatment = typeof row.treatment === "string" ? row.treatment : "";
    const level = typeof row.level === "string" ? row.level : "";
    if (!treatment || !level) continue;
    if (!levels.has(treatment)) levels.set(treatment, new Set());
    levels.get(treatment)!.add(level);
    for (const attribute of Object.keys(contextOf(row))) {
      attributeCounts.set(attribute, (attributeCounts.get(attribute) ?? 0) + 1);
    }
  }
  const levelsByTreatment: Record<string, string[]> = {};
  for (const [treatment, values] of levels) {
    levelsByTreatment[treatment] = [...values].sort();
  }
  const contextAttributes = [...attributeCounts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([attribute]) => attribute);
  return {
    treatments: [...levels.keys()].sort(),
    levelsByTreatment,
    contextAttributes,
  };
}

function generalizeStatus(
  findings: Finding[],
  treatment: string,
  level: string,
  context: Record<string, string>,
): Finding["status"] | null {
  const matches = (finding: Finding) =>
    finding.kind === "generalized" &&
    finding.treatment === treatment &&
    finding.treatment_level === level &&
    sameContext(finding.context ?? {}, context);
  // A merged finding keeps its own status; the primary is found separately.
  const finding = findings.find(matches);
  return finding ? finding.status : null;
}

function sameContext(
  left: Record<string, string>,
  right: Record<string, string>,
): boolean {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) return false;
  return leftKeys.every((key) => right[key] === left[key]);
}

/**
 * The generalized grid: one treatment level across two context axes.
 *
 * Cells whose context has only one of the two axes sit on the `*` row or
 * column instead of being hidden. When two cells land on the same coordinates
 * (a depth-2 and a depth-3 cell), the deeper, more specific one is shown and
 * the other is counted in `hidden` — the table stays honest about what it
 * could not place.
 */
export function generalizedHeatmap(
  report: AuditReport,
  options: {
    treatment: string;
    level: string;
    rowAttribute: string;
    columnAttribute: string;
  },
): GeneralizedHeatmap {
  const findings = report.findings ?? [];
  const { treatment, level, rowAttribute, columnAttribute } = options;
  const rows = discoveryRows(report).filter(
    (row) => row.treatment === treatment && row.level === level,
  );

  const rowValues = new Set<string>();
  const columnValues = new Set<string>();
  let hidden = 0;
  const chosen = new Map<string, Record<string, unknown>>();
  for (const row of rows) {
    const context = contextOf(row);
    const rowValue = context[rowAttribute] ?? ALL_CONTEXTS;
    const columnValue = context[columnAttribute] ?? ALL_CONTEXTS;
    if (rowValue === ALL_CONTEXTS) rowValues.add(ALL_CONTEXTS);
    else rowValues.add(rowValue);
    if (columnValue === ALL_CONTEXTS) columnValues.add(ALL_CONTEXTS);
    else columnValues.add(columnValue);
    const key = `${rowValue}|${columnValue}`;
    const previous = chosen.get(key);
    if (!previous) {
      chosen.set(key, row);
      continue;
    }
    const previousDepth = Number(previous.depth ?? 0);
    const currentDepth = Number(row.depth ?? 0);
    if (
      currentDepth > previousDepth ||
      (currentDepth === previousDepth &&
        Math.abs(Number(row.net_flip_rate ?? 0)) >
          Math.abs(Number(previous.net_flip_rate ?? 0)))
    ) {
      chosen.set(key, row);
    }
    hidden += 1;
  }

  const sortValues = (values: Set<string>) =>
    [...values].sort((left, right) =>
      left === ALL_CONTEXTS
        ? -1
        : right === ALL_CONTEXTS
          ? 1
          : left.localeCompare(right, undefined, { numeric: true }),
    );

  const cells: Record<string, GeneralizedCell> = {};
  for (const [key, row] of chosen) {
    const context = contextOf(row);
    const [rowValue, columnValue] = key.split("|");
    cells[key] = {
      key,
      row: rowValue,
      column: columnValue,
      net: Number(row.net_flip_rate ?? 0),
      n: Number(row.n ?? 0),
      pAdjusted: typeof row.p_adjusted === "number" ? row.p_adjusted : null,
      status: generalizeStatus(findings, treatment, level, context),
      depth: Number(row.depth ?? 0),
      context,
      cellId: String(row.cell ?? key),
    };
  }

  return {
    treatment,
    level,
    rowAttribute,
    columnAttribute,
    rowValues: sortValues(rowValues),
    columnValues: sortValues(columnValues),
    cells,
    hidden,
  };
}

export interface ReportCounts {
  kept: number;
  rejected: number;
  immaterial: number;
  merged: number;
  candidate: number;
}

export function reportCounts(findings: Finding[]): ReportCounts {
  const counts: ReportCounts = {
    kept: 0,
    rejected: 0,
    immaterial: 0,
    merged: 0,
    candidate: 0,
  };
  for (const finding of findings) {
    counts[finding.status] += 1;
  }
  return counts;
}

/** Kept findings first, then merged/rejected/immaterial, preserving report order. */
export function orderedFindings(findings: Finding[]): Finding[] {
  const rank: Record<Finding["status"], number> = {
    kept: 0,
    merged: 1,
    immaterial: 2,
    rejected: 3,
    candidate: 4,
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

export interface SkippedTreatment {
  treatment: string;
  reason: string;
}

export interface SearchSummaryView {
  cellsExamined: number;
  cellsTested: number;
  cellsNotTestable: number;
  discoveryPairs: number;
  confirmationPairs: number;
  candidates: number;
  confirmed: number;
  merged: number;
  plannedApplicants: number;
  probeCap: number;
  cellsBySource: Record<string, number>;
  exhaustiveCells: number;
  skipped: SkippedTreatment[];
  mde: Array<{ n: number; mde: number }>;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : Number(value) || 0;
}

/**
 * The Phase A/B summary written by the generalized search.
 *
 * Returns ``null`` for an old-protocol report, which is how the UI decides
 * whether to render the generalized panel or the fixed intersectional grid.
 */
export function searchSummary(report: AuditReport): SearchSummaryView | null {
  const search = asRecord(asRecord(report.observational)?.search);
  if (!search) return null;
  const plan = asRecord(search.plan) ?? {};
  const skippedRaw = asRecord(plan.skipped_treatments) ?? {};
  const sourcesRaw = asRecord(plan.cells_by_source) ?? {};
  const mdeRaw = search.mde_by_cell_size;
  const mde: Array<{ n: number; mde: number }> = [];
  if (Array.isArray(mdeRaw)) {
    for (const item of mdeRaw) {
      const row = asRecord(item);
      if (!row) continue;
      mde.push({ n: numberValue(row.n), mde: numberValue(row.mde) });
    }
  }
  const cellsBySource: Record<string, number> = {};
  for (const [key, value] of Object.entries(sourcesRaw)) {
    cellsBySource[key] = numberValue(value);
  }
  return {
    cellsExamined: numberValue(search.cells_examined),
    cellsTested: numberValue(search.cells_tested),
    cellsNotTestable: Array.isArray(search.cells_not_testable)
      ? search.cells_not_testable.length
      : 0,
    discoveryPairs: numberValue(search.phase_a_pairs),
    confirmationPairs: numberValue(search.phase_b_pairs),
    candidates: Array.isArray(search.candidates) ? search.candidates.length : 0,
    confirmed: Array.isArray(search.confirmed) ? search.confirmed.length : 0,
    merged: (report.findings ?? []).filter((finding) => finding.status === "merged")
      .length,
    plannedApplicants: numberValue(plan.planned_applicants),
    probeCap: numberValue(plan.probe_cap),
    cellsBySource,
    exhaustiveCells: numberValue(plan.exhaustive_cells),
    skipped: Object.entries(skippedRaw).map(([treatment, reason]) => ({
      treatment,
      reason: String(reason),
    })),
    mde,
  };
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
