import * as React from "react";
import { ArrowRight, Layers, Search } from "lucide-react";

import type { AuditReport, Finding } from "@/api-types";
import { Badge } from "@/components/ui/badge";
import { signedPercent } from "@/lib/arena";
import {
  ALL_CONTEXTS,
  generalizedHeatmap,
  searchDimensions,
  searchSummary,
  type GeneralizedCell,
} from "@/lib/report";
import { probeLabel } from "@/lib/stream";
import { cn } from "@/lib/utils";

function axisLabel(attribute: string): string {
  return attribute === ALL_CONTEXTS ? "all" : probeLabel(attribute);
}

function valueLabel(value: string): string {
  return value === ALL_CONTEXTS ? "all" : value;
}

function heatBackground(net: number): string {
  const magnitude = Math.min(1, Math.abs(net));
  const alpha = 0.1 + magnitude * 0.7;
  return net >= 0
    ? `rgba(251, 113, 133, ${alpha.toFixed(3)})`
    : `rgba(94, 234, 212, ${alpha.toFixed(3)})`;
}

function heatTextClass(net: number): string {
  return net >= 0 ? "text-[#fff1f3]" : "text-[#04211d]";
}

function statusLabel(status: Finding["status"] | null): string {
  if (!status) return "no candidate";
  return status;
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded border border-line/60 bg-canvas/40 px-2 py-1.5">
      <p className="font-mono text-[8.5px] uppercase tracking-[0.12em] text-muted/60">
        {label}
      </p>
      <p className="mt-0.5 font-mono text-[12px] text-ink">{value}</p>
      {hint && <p className="mt-0.5 text-[9px] leading-snug text-muted/70">{hint}</p>}
    </div>
  );
}

function Selector({
  label,
  value,
  options,
  onChange,
  render = (option) => option,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  render?: (option: string) => string;
}) {
  return (
    <label className="flex min-w-[130px] flex-col gap-1">
      <span className="font-mono text-[8.5px] uppercase tracking-[0.13em] text-muted/70">
        {label}
      </span>
      <select
        className="h-8 rounded-md border border-line bg-canvas px-2 font-mono text-[10.5px] text-ink outline-none focus:border-accent/60"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {render(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

/**
 * Phase A/B summary and the selectable treatment x context heatmap.
 *
 * Everything is read from ``report.observational.search``. The panel renders
 * nothing for an old-protocol report rather than inventing a grid.
 */
export function SearchPanel({ report }: { report: AuditReport }) {
  const summary = React.useMemo(() => searchSummary(report), [report]);
  const dimensions = React.useMemo(() => searchDimensions(report), [report]);
  const [treatment, setTreatment] = React.useState(dimensions.treatments[0] ?? "");
  const [level, setLevel] = React.useState("");
  const [rowAttribute, setRowAttribute] = React.useState(
    dimensions.contextAttributes[0] ?? "",
  );
  const [columnAttribute, setColumnAttribute] = React.useState(
    dimensions.contextAttributes[1] ?? dimensions.contextAttributes[0] ?? "",
  );
  const [selected, setSelected] = React.useState<string | null>(null);

  const levels = dimensions.levelsByTreatment[treatment] ?? [];

  React.useEffect(() => {
    if (!dimensions.treatments.includes(treatment)) {
      setTreatment(dimensions.treatments[0] ?? "");
    }
  }, [dimensions.treatments, treatment]);

  React.useEffect(() => {
    if (!levels.includes(level)) setLevel(levels[0] ?? "");
  }, [levels, level]);

  React.useEffect(() => {
    if (!dimensions.contextAttributes.includes(rowAttribute)) {
      setRowAttribute(dimensions.contextAttributes[0] ?? "");
    }
    if (!dimensions.contextAttributes.includes(columnAttribute)) {
      setColumnAttribute(
        dimensions.contextAttributes[1] ?? dimensions.contextAttributes[0] ?? "",
      );
    }
  }, [dimensions.contextAttributes, rowAttribute, columnAttribute]);

  const heatmap = React.useMemo(() => {
    if (!treatment || !level || !rowAttribute || !columnAttribute) return null;
    return generalizedHeatmap(report, {
      treatment,
      level,
      rowAttribute,
      columnAttribute,
    });
  }, [report, treatment, level, rowAttribute, columnAttribute]);

  if (!summary || dimensions.treatments.length === 0) return null;

  const selectedCell: GeneralizedCell | undefined =
    heatmap && selected ? heatmap.cells[selected] : undefined;

  return (
    <section className="panel p-4" aria-label="Generalized search">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="eyebrow">generalized search</p>
          <h3 className="mt-1 flex items-center gap-2 text-[15px] font-semibold">
            <Layers className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
            Treatment × context, discovered then confirmed
          </h3>
          <p className="mt-1 max-w-2xl text-[10.5px] leading-relaxed text-muted">
            Phase A scans every cell and corrects across all of them. Phase B
            re-tests each candidate on fresh twins. The grid below shows Phase A
            net flips; a kept cell also passed Phase B and the Skeptic.
          </p>
        </div>
        <Badge variant="outline">
          {summary.cellsExamined} cells · cap{" "}
          {summary.probeCap.toLocaleString()} applicants
        </Badge>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="phase A"
          value={`${summary.cellsExamined} cells`}
          hint={`${summary.discoveryPairs.toLocaleString()} discovery pairs · ${summary.cellsTested} tested`}
        />
        <Stat
          label="candidates"
          value={String(summary.candidates)}
          hint={
            summary.candidates > summary.confirmed
              ? `${summary.candidates - summary.confirmed} over the confirmation budget`
              : "all went to Phase B"
          }
        />
        <Stat
          label="phase B confirmed"
          value={`${summary.confirmed}`}
          hint={`${summary.confirmationPairs.toLocaleString()} fresh pairs`}
        />
        <Stat
          label="merged"
          value={String(summary.merged)}
          hint={
            summary.merged > 0
              ? "overlapping kept cells folded into one primary"
              : "no redundant kept cells"
          }
        />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[9.5px] text-muted/75">
        <span>
          plan: {Object.entries(summary.cellsBySource)
            .map(([source, count]) => `${source} ${count}`)
            .join(" · ") || "not recorded"}
        </span>
        <span>exhaustive grid would be {summary.exhaustiveCells} cells</span>
        <span>
          planned {summary.plannedApplicants.toLocaleString()} applicants
        </span>
        {summary.skipped.length > 0 && (
          <span>
            skipped:{" "}
            {summary.skipped
              .map((entry) => `${entry.treatment} (${entry.reason})`)
              .join("; ")}
          </span>
        )}
      </div>

      {summary.mde.length > 0 && (
        <p className="mt-2 font-mono text-[9.5px] leading-relaxed text-muted/70">
          MDE (power 0.80, assumed discordance 0.25):{" "}
          {summary.mde
            .map((row) => `n=${row.n.toLocaleString()} → ${row.mde.toFixed(3)}`)
            .join(" · ")}
          . Planning approximations, not post-hoc power.
        </p>
      )}

      {heatmap && (
        <div className="mt-4 border-t border-line/60 pt-3">
          <div className="flex flex-wrap items-end gap-2">
            <Selector
              label="treatment"
              value={treatment}
              options={dimensions.treatments}
              onChange={setTreatment}
              render={probeLabel}
            />
            <Selector
              label="level (vs comparison)"
              value={level}
              options={levels}
              onChange={setLevel}
            />
            <Selector
              label="context rows"
              value={rowAttribute}
              options={dimensions.contextAttributes}
              onChange={setRowAttribute}
              render={probeLabel}
            />
            <Selector
              label="context columns"
              value={columnAttribute}
              options={dimensions.contextAttributes}
              onChange={setColumnAttribute}
              render={probeLabel}
            />
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[520px] border-separate border-spacing-1">
              <caption className="sr-only">
                Generalized discovery net flip rate for {probeLabel(treatment)}{" "}
                level {level}, rows {probeLabel(rowAttribute)}, columns{" "}
                {probeLabel(columnAttribute)}
              </caption>
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left font-mono text-[9px] uppercase tracking-[0.12em] text-muted/60">
                    {axisLabel(rowAttribute)} · {axisLabel(columnAttribute)}
                  </th>
                  {heatmap.columnValues.map((column) => (
                    <th
                      key={column}
                      className="px-2 py-1 text-center font-mono text-[9px] uppercase tracking-[0.12em] text-muted/60"
                    >
                      {axisLabel(columnAttribute)} = {valueLabel(column)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmap.rowValues.map((row) => (
                  <tr key={row}>
                    <th className="whitespace-nowrap px-2 py-1 text-left font-mono text-[10px] font-normal text-muted">
                      {axisLabel(rowAttribute)} = {valueLabel(row)}
                    </th>
                    {heatmap.columnValues.map((column) => {
                      const cell = heatmap.cells[`${row}|${column}`];
                      if (!cell) {
                        return (
                          <td
                            key={column}
                            className="rounded border border-line/40 bg-canvas/20 px-2 py-2 text-center font-mono text-[10px] text-muted/40"
                          >
                            not scanned
                          </td>
                        );
                      }
                      const isSelected = selected === cell.key;
                      return (
                        <td key={column} className="p-0">
                          <button
                            type="button"
                            onClick={() =>
                              setSelected(isSelected ? null : cell.key)
                            }
                            aria-pressed={isSelected}
                            title={`${cell.cellId} · ${cell.n} pairs`}
                            className={cn(
                              "w-full rounded border px-2 py-2 text-left",
                              heatTextClass(cell.net),
                              isSelected
                                ? "border-accent ring-1 ring-accent/60"
                                : "border-line/40",
                            )}
                            style={{ backgroundColor: heatBackground(cell.net) }}
                          >
                            <span className="block font-mono text-[11px]">
                              {signedPercent(cell.net)}
                            </span>
                            <span className="block font-mono text-[8.5px] uppercase tracking-[0.1em] opacity-80">
                              {statusLabel(cell.status)}
                            </span>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-[9px] text-muted/70">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-4 rounded-sm bg-[rgba(94,234,212,0.55)]" />
              0 pp
            </span>
            <span>→</span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-4 rounded-sm bg-[rgba(251,113,133,0.8)]" />
              100 pp harm
            </span>
            <span>
              `all` means the cell does not condition on that axis. Select a cell
              for its context and cell id.
            </span>
            {heatmap.hidden > 0 && (
              <span>
                {heatmap.hidden} deeper cell
                {heatmap.hidden === 1 ? "" : "s"} share a coordinate with a shown
                cell
              </span>
            )}
          </div>

          {selectedCell ? (
            <div className="mt-2 rounded-lg border border-line/60 bg-canvas/40 px-3 py-2">
              <p className="font-mono text-[10px] text-ink">
                <Search className="mr-1 inline h-3 w-3 text-accent" aria-hidden="true" />
                {selectedCell.cellId}
              </p>
              <p className="mt-1 font-mono text-[9.5px] leading-relaxed text-muted">
                treatment {probeLabel(treatment)} = {level} · context{" "}
                {Object.entries(selectedCell.context)
                  .map(([key, value]) => `${probeLabel(key)}=${value}`)
                  .join(", ") || "none"}{" "}
                · depth {selectedCell.depth} · {selectedCell.n} pairs ·{" "}
                {selectedCell.status ? statusLabel(selectedCell.status) : "no finding"}
              </p>
            </div>
          ) : null}
        </div>
      )}

      <p className="mt-3 flex items-center gap-1.5 text-[10px] leading-relaxed text-muted/60">
        <ArrowRight className="h-3 w-3" aria-hidden="true" />
        Discovery cells are shown even when they produced no candidate. A cell
        that was not in the pre-registered panel says “not scanned” rather than
        showing a zero.
      </p>
    </section>
  );
}
