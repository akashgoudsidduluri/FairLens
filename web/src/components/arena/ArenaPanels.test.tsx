import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentLanes } from "@/components/arena/AgentLanes";
import { BudgetPanel } from "@/components/arena/BudgetPanel";
import { EarlyStopBanner } from "@/components/arena/EarlyStopBanner";
import { FlippedTray } from "@/components/arena/FlippedTray";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeAgent, makeProbe } from "@/test/fixtures";

describe("AgentLanes", () => {
  it("shows the current action in each of the four lanes", () => {
    const events = [
      makeAgent({ agent: "planner", message: "planning 4 attribute probes" }),
      makeAgent({ agent: "statistician", message: "estimating the running rate" }),
      makeAgent({ agent: "skeptic", message: "challenging a candidate finding" }),
      makeAgent({ agent: "impact", message: "translating flips into people" }),
    ];
    render(<AgentLanes events={events} status="open" />);

    expect(screen.getByText("Prober")).toBeInTheDocument();
    expect(screen.getByText("Statistician")).toBeInTheDocument();
    expect(screen.getByText("Skeptic")).toBeInTheDocument();
    expect(screen.getByText("Reporter")).toBeInTheDocument();
    expect(screen.getByText("planning 4 attribute probes")).toBeInTheDocument();
    expect(screen.getByText("estimating the running rate")).toBeInTheDocument();
    expect(screen.getByText("challenging a candidate finding")).toBeInTheDocument();
    expect(screen.getByText("translating flips into people")).toBeInTheDocument();
    expect(
      screen.getByTitle(/plain-language impact/).getAttribute("aria-current"),
    ).toBe("step");
  });

  it("marks empty lanes as waiting", () => {
    render(<AgentLanes events={[]} status="connecting" />);
    expect(screen.getAllByText(/waiting for its first action/)).toHaveLength(4);
  });
});

describe("EarlyStopBanner", () => {
  it("explains a sequential stop in plain language", () => {
    render(
      <EarlyStopBanner
        stop={{
          attribute: "gender",
          n: 1200,
          requestedN: 2000,
          reason: "stop_material_harm",
          message:
            "the live interval is already above the materiality line, so enough evidence of material harm has accumulated",
        }}
      />,
    );
    expect(screen.getByText(/Stopped early on gender/)).toBeInTheDocument();
    expect(screen.getByText("1,200 / 2,000 pairs checked")).toBeInTheDocument();
    expect(screen.getByText("sequential stop")).toBeInTheDocument();
    expect(screen.getByText("rule fixed before the audit")).toBeInTheDocument();
  });
});

describe("FlippedTray", () => {
  it("keeps flipped pairs and their decision transition", () => {
    render(
      <FlippedTray
        flips={[
          makeProbe({ pair_index: 4 }),
          makeProbe({ pair_index: 3, original_approved: false, twin_approved: true }),
        ]}
      />,
    );
    expect(screen.getByText("2 kept")).toBeInTheDocument();
    expect(screen.getByText("#5 · gender")).toBeInTheDocument();
    expect(screen.getByText("#4 · gender")).toBeInTheDocument();
    expect(screen.getAllByText("single-gender-female").length).toBeGreaterThan(0);
  });

  it("invites the first flip when the tray is empty", () => {
    render(<FlippedTray flips={[]} />);
    expect(screen.getByText(/no flips yet/)).toBeInTheDocument();
  });
});

describe("BudgetPanel", () => {
  it("shows applicants spent, the hard cap, the rate, and stream health", () => {
    render(
      <TooltipProvider>
        <BudgetPanel
          probeCount={120}
          probeCap={100000}
          nPairs={2000}
          rate={42.5}
          status="open"
          lastEventId={480}
          reconnects={2}
          startedAt={Date.now()}
          sequentialEnabled
        />
      </TooltipProvider>,
    );
    expect(
      screen.getByText(
        (_content, element) =>
          element?.tagName === "P" &&
          element.textContent === "240 / 100,000 applicants",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "240");
    expect(screen.getByText("42.5 pairs/s")).toBeInTheDocument();
    expect(screen.getByText("2,000")).toBeInTheDocument();
    expect(screen.getByText("event #480")).toBeInTheDocument();
    expect(screen.getByText("pre-registered · on")).toBeInTheDocument();
    expect(screen.getByText("resumed 2×")).toBeInTheDocument();
  });
});
