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

  it("shows a retry state when the API fails", async () => {
    const { ApiError } = await import("@/lib/api");
    getEvidence.mockRejectedValue(new ApiError(500, "results unavailable"));

    renderPage();

    expect(await screen.findByText(/results unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
