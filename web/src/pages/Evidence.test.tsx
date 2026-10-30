import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EvidenceReport } from "@/api-types";
import { api } from "@/lib/api";
import { Evidence } from "@/pages/Evidence";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, getEvidence: vi.fn() },
  };
});

const getEvidence = vi.mocked(api.getEvidence);

function payload(): EvidenceReport {
  return {
    generated_at: "2026-10-28T00:00:00Z",
    sandbox: {
      runs: 10,
      expectation_passed: 5,
      expectation_total: 10,
      false_alarm_before: 2,
      false_alarm_after: 0,
      sources: [
        { path: "eval/results/results.csv", present: true },
        { path: "eval/results/summary.md", present: false },
      ],
      models: [
        {
          model_id: 1,
          runs: 5,
          expectation_passed: 5,
          expectation_total: 5,
          kept_mean: 0,
          kept_min: 0,
          kept_max: 0,
          rejected_mean: 8,
          immaterial_mean: 0,
          false_alarm_before: 2,
          false_alarm_after: 0,
          false_alarm_runs: 5,
          runtime_mean_s: 22,
          number_check_passed: 5,
          misses: [],
        },
        {
          model_id: 5,
          runs: 5,
          expectation_passed: 0,
          expectation_total: 5,
          kept_mean: 2,
          kept_min: 2,
          kept_max: 2,
          rejected_mean: 6,
          immaterial_mean: 0,
          false_alarm_before: null,
          false_alarm_after: null,
          false_alarm_runs: 0,
          runtime_mean_s: 26,
          number_check_passed: 5,
          misses: ["single-attribute gender was kept (expected immaterial)"],
        },
      ],
    },
    suite_b: {
      runs: 4,
      expectation_passed: 2,
      expectation_total: 4,
      markdown:
        "# Suite B and the generalized protocol (R5 Step 7)\n\nLimitations stay attached.",
      sources: [
        { path: "eval/results/suite_b.csv", present: true },
        { path: "eval/results/suite_b_fairlearn.csv", present: true },
        { path: "eval/results/suite_b.md", present: true },
      ],
      models: [
        {
          model_id: 8,
          runs: 2,
          expectation_passed: 2,
          expectation_total: 2,
          kept_mean: 1,
          kept_min: 1,
          kept_max: 1,
          candidates_mean: 16,
          confirmed_mean: 16,
          cells_examined: 110,
          false_alarm_before: 54,
          false_alarm_after: 2,
          runtime_mean_s: 61,
          mde_n200: 0.099,
          mde_n1000: 0.044,
          kept_ids: ["gen-age-45plus-credit_score-high"],
          misses: [],
          notes: [
            "kept age finding is context-specific, not the pre-registered main effect",
          ],
          dose_response: ["45:+0.0000; 55:+0.6100"],
          max_dp_gap: 0.31,
          max_dp_attribute: "age_band",
        },
        {
          model_id: 9,
          runs: 2,
          expectation_passed: 0,
          expectation_total: 2,
          kept_mean: 8,
          kept_min: 8,
          kept_max: 8,
          candidates_mean: 16,
          confirmed_mean: 16,
          cells_examined: 110,
          false_alarm_before: 30,
          false_alarm_after: 6,
          runtime_mean_s: 61,
          mde_n200: 0.099,
          mde_n1000: 0.044,
          kept_ids: ["gen-pincode_group-p2-gender-female-loan_amount-high"],
          misses: ["expected exactly one kept finding, got 9"],
          notes: [],
          dose_response: [],
          max_dp_gap: 0.39,
          max_dp_attribute: "pincode_group",
        },
      ],
    },
    suite_b_r51: {
      runs: 4,
      expectation_passed: 3,
      expectation_total: 4,
      markdown:
        "# R5.1 sibling-context merge - protocol 2\n\nDesigned after protocol 1 was reported.",
      sources: [
        { path: "eval/results/suite_b_r51.csv", present: true },
        { path: "eval/results/suite_b_r51_fairlearn.csv", present: true },
        { path: "eval/results/suite_b_r51.md", present: true },
      ],
      models: [
        {
          model_id: 8,
          runs: 2,
          expectation_passed: 2,
          expectation_total: 2,
          kept_mean: 1,
          kept_min: 1,
          kept_max: 1,
          candidates_mean: 16,
          confirmed_mean: 16,
          cells_examined: 110,
          false_alarm_before: 10,
          false_alarm_after: 2,
          runtime_mean_s: 71,
          mde_n200: 0.099,
          mde_n1000: 0.044,
          kept_ids: ["gen-age-45plus-credit_score-high"],
          misses: [],
          notes: [],
          dose_response: ["45:+0.0000; 55:+0.6100"],
          max_dp_gap: 0.31,
          max_dp_attribute: "age_band",
        },
        {
          model_id: 9,
          runs: 2,
          expectation_passed: 1,
          expectation_total: 2,
          kept_mean: 1.5,
          kept_min: 1,
          kept_max: 2,
          candidates_mean: 16,
          confirmed_mean: 16,
          cells_examined: 110,
          false_alarm_before: 30,
          false_alarm_after: 3,
          runtime_mean_s: 71,
          mde_n200: 0.099,
          mde_n1000: 0.044,
          kept_ids: ["gen-pincode_group-p2-gender-female-loan_amount-high"],
          misses: ["expected exactly one kept finding, got 2"],
          notes: [],
          dose_response: [],
          max_dp_gap: 0.39,
          max_dp_attribute: "pincode_group",
        },
      ],
    },
    real: {
      markdown: "# Real-data target results\n\n**Status: evaluated after pre-registration.**",
      sources: [
        { path: "eval/results/real_models.csv", present: true },
        { path: "eval/results/real_models.md", present: true },
      ],
      models: [
        {
          model: "adult_income",
          label: "UCI Adult Income",
          runs: 5,
          supported_probes: ["gender"],
          skipped_probes: ["intersectional"],
          kept_mean: 0,
          rejected_mean: 0,
          immaterial_mean: 1,
          impact_per_10k_mean: 80,
          impact_per_10k_min: 50,
          impact_per_10k_max: 120,
          holdout_accuracy: 0.875,
          holdout_auc: 0.93,
          fairlearn: [
            {
              attribute: "sex",
              demographic_parity_difference: 0.178,
              equalized_odds_difference: 0.068,
            },
          ],
          notes: ["gender=female: net=+0.0065 below the threshold 0.02."],
          errors: [],
        },
      ],
    },
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/evidence"]}>
      <Routes>
        <Route path="/evidence" element={<Evidence />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Evidence page", () => {
  beforeEach(() => {
    getEvidence.mockReset();
    getEvidence.mockResolvedValue(payload());
  });

  it("shows expected vs found and false alarms from the API", async () => {
    renderPage();

    expect(await screen.findByText(/what the evaluation actually found/i)).toBeInTheDocument();
    expect(screen.getByText("5/10 expectations met")).toBeInTheDocument();
    expect(screen.getByText("5 / 10")).toBeInTheDocument();
    expect(screen.getByText("2 → 0")).toBeInTheDocument();
    expect(screen.getByText("0/5 met")).toBeInTheDocument();
    expect(screen.getByText("5/5 met")).toBeInTheDocument();
  });

  it("states the pre-registration miss plainly", async () => {
    renderPage();

    expect(
      await screen.findByText(/model 5 missed its pre-registration/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/0 of 5 seeds met the stated expectation/i)).toBeInTheDocument();
    expect(
      screen.getByText("single-attribute gender was kept (expected immaterial)"),
    ).toBeInTheDocument();
  });

  it("shows real-model results next to Fairlearn metrics", async () => {
    renderPage();

    const card = await screen.findByRole("article", { name: /UCI Adult Income evidence/i });
    expect(within(card).getByText("80 / 10k")).toBeInTheDocument();
    expect(within(card).getByText("87.5%")).toBeInTheDocument();
    expect(within(card).getByText("17.8%")).toBeInTheDocument();
    expect(within(card).getByText("6.8%")).toBeInTheDocument();
    expect(within(card).getByText("1 unsupported probe skipped")).toBeInTheDocument();
  });

  it("keeps the verbatim notes and missing-file markers visible", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: /full protocol and limitations/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Status: evaluated after pre-registration/)).toBeInTheDocument();
    expect(screen.getByText("eval/results/summary.md")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
  });

  it("shows suite B kept findings, confirmation counts, and the Fairlearn gap", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", {
        name: /treatment × context, discovered then confirmed/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("2/2 met").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/gen-age-45plus-credit_score-high/),
    ).toBeInTheDocument();
    expect(screen.getByText(/context-specific, not the pre-registered main effect/)).toBeInTheDocument();
    expect(screen.getAllByText(/suite_b\.md/).length).toBeGreaterThan(0);
  });

  it("shows protocol 2 next to protocol 1 with the headline deltas", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", {
        name: /treatment × context, discovered then confirmed/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("P1 2/4 met")).toBeInTheDocument();
    expect(screen.getByText("P2 3/4 met")).toBeInTheDocument();
    expect(screen.getByText("2/4 → 3/4")).toBeInTheDocument();
    expect(screen.getByText("4.5 → 1.3")).toBeInTheDocument();
    expect(screen.getByText("8 → 5")).toBeInTheDocument();
    expect(
      screen.getByText(/protocol 2 is a refinement, not a clean first pass/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/designed after protocol 1's results/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/suite_b_r51\.md/).length).toBeGreaterThan(0);
    expect(screen.getByText("MISS · expected exactly one kept finding, got 2")).toBeInTheDocument();
  });

  it("shows a retry state when the API fails", async () => {
    const { ApiError } = await import("@/lib/api");
    getEvidence.mockRejectedValue(new ApiError(500, "results unavailable"));

    renderPage();

    expect(await screen.findByText(/results unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
