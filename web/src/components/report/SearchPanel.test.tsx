import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { SearchPanel } from "@/components/report/SearchPanel";
import { makeSearchReport } from "@/test/fixtures";

describe("SearchPanel", () => {
  it("reports Phase A, candidates, Phase B, and merged cells", () => {
    render(<SearchPanel report={makeSearchReport()} />);

    expect(
      screen.getByRole("heading", {
        name: /treatment × context, discovered then confirmed/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("7 cells")).toBeInTheDocument();
    expect(
      screen.getByText(/14,000 discovery pairs · 7 tested/),
    ).toBeInTheDocument();
    expect(screen.getByText(/800 fresh pairs/)).toBeInTheDocument();
    expect(
      screen.getByText(/overlapping kept cells folded into one primary/),
    ).toBeInTheDocument();
    expect(screen.getByText(/exhaustive grid would be 109 cells/)).toBeInTheDocument();
    expect(
      screen.getByText(/planned 68,800 applicants/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/n=200 → 0\.099 · n=1,000 → 0\.044/),
    ).toBeInTheDocument();
  });

  it("shows the kept cell and counts the deeper cell that shares its coordinate", async () => {
    const user = userEvent.setup();
    render(<SearchPanel report={makeSearchReport()} />);

    await user.selectOptions(screen.getByLabelText(/level/i), "45+");
    const grid = screen.getByRole("table");
    expect(within(grid).getByText("+61.00%")).toBeInTheDocument();
    // credit_score=low has a depth-1 cell and a deeper credit_score=low,
    // age_band=45+ cell; the deeper one is drawn and the other is counted.
    expect(within(grid).getByText("+3.00%")).toBeInTheDocument();
    expect(
      screen.getByText(/1 deeper cell share a coordinate/i),
    ).toBeInTheDocument();
    expect(within(grid).getAllByText("kept")).toHaveLength(1);
  });

  it("lets the reader pick a treatment level and inspect a cell", async () => {
    const user = userEvent.setup();
    render(<SearchPanel report={makeSearchReport()} />);

    const level = screen.getByLabelText(/level/i);
    // Levels are sorted, so the pre-registered main-effect level is not
    // necessarily the default; the reader picks it.
    expect(level).toHaveValue("35-44");
    const before = screen.getByRole("table");
    expect(within(before).getByText("+0.00%")).toBeInTheDocument();

    await user.selectOptions(level, "45+");
    const keptCell = within(screen.getByRole("table")).getByRole("button", {
      name: /\+61\.00%/,
    });
    await user.click(keptCell);
    expect(keptCell).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByText(/gen-age-45plus-credit_score-high/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/credit score=high · depth 1 · 2000 pairs/),
    ).toBeInTheDocument();
  });
});
