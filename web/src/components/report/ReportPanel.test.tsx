import * as React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditRecord, AuditReport } from "@/api-types";
import { ReportPanel } from "@/components/report/ReportPanel";
import { api } from "@/lib/api";
import { makeAgent, makeFinding, makeReport } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      decide: vi.fn(),
      startAudit: vi.fn(),
    },
  };
});

const decide = vi.mocked(api.decide);
const startAudit = vi.mocked(api.startAudit);

function record(overrides: Partial<AuditRecord> = {}): AuditRecord {
  return {
    id: "run1",
    status: "completed",
    model_id: 2,
    target: "sandbox:2",
    api_url: "http://127.0.0.1:8010",
    seed: 42,
    include_mitigation: false,
    include_narrative: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function report(): AuditReport {
  return makeReport({
    findings: [
      makeFinding(),
      makeFinding({
        id: "single-pincode_group-p2",
        attribute_or_subgroup: "pincode_group=P2",
        target_group: "P2",
        comparison_group: "P1",
        status: "rejected",
        reason:
          "Rejected as confounded: the observational gap is not accompanied by a material counterfactual effect.",
        evidence: {
          n: 2000,
          b: 12,
          c: 8,
          net_flip_rate: 0.002,
          ci_low: -0.001,
          ci_high: 0.005,
          p_raw: 0.4,
          p_adjusted: 0.9,
        },
      }),
      makeFinding({
        id: "intersectional-female-35-44-urban",
        kind: "intersectional",
        attribute_or_subgroup: "gender=female|age_band=35-44|urban_rural=urban",
        target_group: "female|35-44|urban",
        comparison_group: "male|35-44|urban",
        status: "kept",
        evidence: {
          n: 420,
          b: 260,
          c: 0,
          net_flip_rate: 0.619,
          ci_low: 0.57,
          ci_high: 0.66,
          p_raw: 0,
          p_adjusted: 0,
        },
      }),
    ],
    impact: [
      {
        finding_id: "single-gender-female",
        subgroup: "female",
        net_flip_rate: 0.6535,
        per_10k: 7200,
        ci_low_per_10k: 6330,
        ci_high_per_10k: 6735,
        explanation: "About 7,200 women per 10,000 lose an approval they deserve.",
      },
    ],
    observational: {
      intersectional_cells: [
        {
          target_gender: "female",
          age_band: "35-44",
          urban_rural: "urban",
          n: 420,
          net_flip_rate: 0.619,
          p_adjusted: 0,
        },
        {
          target_gender: "male",
          age_band: "35-44",
          urban_rural: "urban",
          n: 420,
          net_flip_rate: 0.01,
          p_adjusted: 0.8,
        },
        {
          target_gender: "female",
          age_band: "45+",
          urban_rural: "rural",
          n: 180,
          net_flip_rate: 0.08,
          p_adjusted: 0.4,
        },
      ],
    },
    narrative: "About 7,200 women per 10,000 lose an approval.",
    number_check_result: { passed: true, source: "template" },
  });
}

function skepticEvents() {
  return [
    makeAgent({
      agent: "skeptic",
      message: "challenging gender",
      payload: {
        finding_id: "single-gender-female",
        status: "kept",
        checks: [
          { name: "min_sample_size", passed: true, detail: "2,000 pairs observed." },
          { name: "significance_after_correction", passed: true, detail: "Holm p < 1e-300." },
          { name: "materiality", passed: true, detail: "0.6535 >= 0.02." },
          { name: "symmetric_noise", passed: true, detail: "b=1307, c=0." },
          { name: "income_matched_persistence", passed: true, detail: "Still 0.61 inside quintiles." },
          { name: "confounding_check", passed: true, detail: "No legitimate explanation." },
        ],
      },
    }),
    makeAgent({
      agent: "skeptic",
      message: "challenging region group",
      payload: {
        finding_id: "single-pincode_group-p2",
        status: "rejected",
        checks: [
          { name: "min_sample_size", passed: true, detail: "2,000 pairs observed." },
          { name: "significance_after_correction", passed: false, detail: "Holm p = 0.9." },
          { name: "materiality", passed: false, detail: "0.002 < 0.02." },
          { name: "symmetric_noise", passed: true, detail: "b=12, c=8." },
          { name: "income_matched_persistence", passed: false, detail: "Effect vanishes inside quintiles." },
          { name: "confounding_check", passed: false, detail: "Observational gap with no counterfactual effect." },
        ],
      },
    }),
  ];
}

function renderPanel(
  props: Partial<React.ComponentProps<typeof ReportPanel>> = {},
) {
  const onDecided = vi.fn();
  const view = render(
    <MemoryRouter initialEntries={["/audit/run1"]}>
      <Routes>
        <Route path="/certificates" element={<p>certificate page</p>} />
        <Route
          path="/audit/:auditId"
          element={
            <ReportPanel
              record={record()}
              report={report()}
              agentEvents={skepticEvents()}
              onDecided={onDecided}
              {...props}
            />
          }
        />
        <Route path="/audit/new-run" element={<p>rerun audit</p>} />
        <Route path="/replay/:replayId" element={<p>replay page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return { ...view, onDecided };
}

describe("ReportPanel", () => {
  beforeEach(() => {
    decide.mockReset();
    startAudit.mockReset();
  });

  it("shows kept and rejected stamps with every Skeptic check", () => {
    renderPanel();

    expect(screen.getByText("2 kept")).toBeInTheDocument();
    expect(screen.getByText("1 rejected")).toBeInTheDocument();
    expect(
      screen.getByLabelText("KEPT finding Gender: female vs male"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("REJECTED finding Region group: P2 vs P1"),
    ).toBeInTheDocument();

    const kept = screen.getByLabelText("KEPT finding Gender: female vs male");
    expect(within(kept).getByText("+65.35%")).toBeInTheDocument();
    expect(within(kept).getByText("+63.30% to +67.35%")).toBeInTheDocument();
    expect(within(kept).getByText("p < 1e-300")).toBeInTheDocument();
    expect(within(kept).getByText("income-matched re-test")).toBeInTheDocument();
    expect(within(kept).getAllByLabelText("passed")).toHaveLength(6);

    // Failures stay visible; a rejected candidate is not deleted.
    const rejected = screen.getByLabelText(
      "REJECTED finding Region group: P2 vs P1",
    );
    expect(within(rejected).getAllByLabelText("failed")).toHaveLength(4);
    expect(
      within(rejected).getByText(/Rejected as confounded/),
    ).toBeInTheDocument();
    expect(
      within(rejected).getByText("significance after correction"),
    ).toBeInTheDocument();
  });

  it("renders the intersectional grid with fixed-scale cells and controls", () => {
    renderPanel();

    const heatmap = screen.getByLabelText("Intersectional heatmap");
    expect(within(heatmap).getByText("age · location")).toBeInTheDocument();
    expect(within(heatmap).getByText("female target")).toBeInTheDocument();
    expect(within(heatmap).getByText("male target")).toBeInTheDocument();
    expect(within(heatmap).getByText("35-44 · urban")).toBeInTheDocument();
    expect(within(heatmap).getByText("45+ · rural")).toBeInTheDocument();
    expect(within(heatmap).getByText("+61.90%")).toBeInTheDocument();
    expect(within(heatmap).getByText("+1.00%")).toBeInTheDocument();
    expect(within(heatmap).getByText("+8.00%")).toBeInTheDocument();
    expect(within(heatmap).getByText("kept")).toBeInTheDocument();
    expect(within(heatmap).getAllByText("no candidate")).toHaveLength(2);
    expect(within(heatmap).getByText(/not scanned/)).toBeInTheDocument();
    expect(within(heatmap).getByText(/fixed at 0–100 percentage points/)).toBeInTheDocument();
  });

  it("counts the human impact and does not invent one when nothing survives", () => {
    const view = renderPanel();
    const impact = screen.getByLabelText("Human impact");
    expect(within(impact).getByText("7,200")).toBeInTheDocument();
    expect(within(impact).getByText(/6,330–6,735/)).toBeInTheDocument();
    expect(within(impact).getByText(/No hidden multiplier/)).toBeInTheDocument();

    view.rerender(
      <MemoryRouter initialEntries={["/audit/run1"]}>
        <ReportPanel
          record={record()}
          report={makeReport({ findings: [], impact: [] })}
          agentEvents={[]}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/no per-10,000 claim is invented/i),
    ).toBeInTheDocument();
  });

  it("blocks sign-off without a name and issues a certificate with one", async () => {
    const user = userEvent.setup();
    decide.mockResolvedValue({
      audit: record({
        decision: {
          approver: "Dr A. Rao",
          decision: "approve",
          certificate_index: 0,
          decided_at: "2026-01-01T00:05:00Z",
        },
      }),
      certificate: {
        index: 0,
        prev_hash: "0".repeat(64),
        record_hash: "a".repeat(64),
        payload: { approver: "Dr A. Rao", decision: "approve" },
        created_at: "2026-01-01T00:05:00Z",
      },
    });
    const { onDecided } = renderPanel();

    const approve = screen.getByRole("button", {
      name: /approve & issue certificate/i,
    });
    expect(approve).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /^reject$/i }),
    ).toBeDisabled();

    await user.type(screen.getByLabelText("Approver name"), "Dr A. Rao");
    expect(approve).toBeEnabled();
    await user.click(approve);

    expect(decide).toHaveBeenCalledWith("run1", "Dr A. Rao", "approve");
    const signOff = screen.getByLabelText("Human sign-off");
    expect(
      (await within(signOff).findAllByText("Dr A. Rao")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/certificate #0/)).toBeInTheDocument();
    expect(screen.getByText(/tamper-evident/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /open the certificate chain/i }),
    ).toHaveAttribute("href", "/certificates");
    expect(onDecided).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: expect.objectContaining({ approver: "Dr A. Rao" }),
      }),
    );
  });

  it("runs a completed sandbox audit again against the same target and seed", async () => {
    const user = userEvent.setup();
    startAudit.mockResolvedValue({
      id: "new-run",
      events_url: "/audits/new-run/events",
      result_url: "/audits/new-run",
    });
    renderPanel();

    await user.click(screen.getByRole("button", { name: /run again/i }));

    expect(startAudit).toHaveBeenCalledWith({
      model_id: 2,
      target: "sandbox:2",
      seed: 42,
      include_mitigation: false,
      include_narrative: true,
    });
    expect(await screen.findByText("rerun audit")).toBeInTheDocument();
  });

  it("refuses to run a connected endpoint again, which is not stored", () => {
    renderPanel({
      record: record({ target: "inline:connected-endpoint" }),
    });

    const again = screen.getByRole("button", { name: /run again/i });
    expect(again).toBeDisabled();
    expect(again).toHaveAttribute(
      "title",
      "A connected endpoint is not stored, so it cannot be run again",
    );
  });

  it("opens the recording instead of starting a job when Replay is clicked", async () => {
    const user = userEvent.setup();
    renderPanel({ record: record({ replay_id: "sandbox-2-seed-42" }) });

    await user.click(screen.getByRole("button", { name: /^replay$/i }));

    expect(startAudit).not.toHaveBeenCalled();
    expect(await screen.findByText("replay page")).toBeInTheDocument();
  });

  it("disables Replay when no recording exists and keeps sign-off read-only in replay mode", () => {
    renderPanel({ mode: "replay" });

    expect(screen.queryByRole("button", { name: /^replay$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/read-only recording/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/approver name/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve & issue certificate/i }),
    ).not.toBeInTheDocument();
  });
});
