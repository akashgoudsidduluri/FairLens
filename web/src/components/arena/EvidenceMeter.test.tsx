import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { EvidenceMeter } from "@/components/arena/EvidenceMeter";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeProbe } from "@/test/fixtures";

function renderMeter(events = [makeProbe()]) {
  render(
    <TooltipProvider>
      <EvidenceMeter
        events={events}
        materiality={0.02}
        ciLevel={0.95}
        bootstrapIterations={4000}
      />
    </TooltipProvider>,
  );
}

describe("EvidenceMeter", () => {
  it("shows the running rate, its live interval, and the materiality call", () => {
    renderMeter([
      makeProbe({ pair_index: 0, b_running: 1, c_running: 0, n_running: 1, net_flip_rate_running: 1 }),
      makeProbe({ pair_index: 1, b_running: 2, c_running: 0, n_running: 2, net_flip_rate_running: 1 }),
      makeProbe({
        pair_index: 2,
        b_running: 2,
        c_running: 1,
        n_running: 3,
        net_flip_rate_running: 1 / 3,
        ci_low_running: 0,
        ci_high_running: 0.1,
      }),
    ]);
    expect(screen.getByText("+33.33%")).toBeInTheDocument();
    expect(screen.getByText(/95% CI \[\+0\.00%, \+10\.00%\]/)).toBeInTheDocument();
    expect(screen.getByText("above materiality")).toBeInTheDocument();
    expect(screen.getByText("lost approval")).toBeInTheDocument();
    expect(screen.getByText("gained approval")).toBeInTheDocument();
    expect(screen.getByText(/normal approximation/)).toBeInTheDocument();
    expect(screen.getByText(/final findings use the seeded bootstrap/)).toBeInTheDocument();
  });

  it("says below materiality when the running rate is small", () => {
    renderMeter([
      makeProbe({
        b_running: 0,
        c_running: 0,
        n_running: 1,
        net_flip_rate_running: 0,
        ci_low_running: -0.01,
        ci_high_running: 0.01,
      }),
    ]);
    expect(screen.getByText("below materiality")).toBeInTheDocument();
    expect(screen.getByText("+0.00%")).toBeInTheDocument();
  });

  it("waits for pairs instead of inventing a rate", () => {
    renderMeter([]);
    expect(screen.getByText(/waiting for pairs/)).toBeInTheDocument();
    expect(screen.queryByText("above materiality")).not.toBeInTheDocument();
  });

  it("keeps earlier attribute evidence visible when a new probe starts at zero", async () => {
    const user = userEvent.setup();
    renderMeter([
      makeProbe({
        pair_index: 1999,
        b_running: 40,
        c_running: 0,
        n_running: 2000,
        net_flip_rate_running: 0.02,
        ci_low_running: 0.014,
        ci_high_running: 0.026,
      }),
      makeProbe({
        probe_id: "single-pincode_group-female",
        pair_index: 0,
        changed_field: "pincode_group",
        b_running: 0,
        c_running: 0,
        n_running: 1,
        net_flip_rate_running: 0,
        ci_low_running: 0,
        ci_high_running: 0,
      }),
    ]);

    const group = screen.getByRole("group", { name: /evidence by attribute/i });
    expect(group).toHaveTextContent("gender +2.00%");
    expect(group).toHaveTextContent("region group +0.00%");

    // The headline follows the probe that is still streaming…
    expect(screen.getByText(/over 1 pairs · region group/)).toBeInTheDocument();
    expect(screen.getByText("below materiality")).toBeInTheDocument();

    // …but one click brings the finished attribute back.
    await user.click(screen.getByRole("button", { name: /gender \+2\.00%/ }));
    expect(screen.getByText(/over 2K pairs · gender/)).toBeInTheDocument();
    expect(screen.getByText(/95% CI \[\+1\.40%, \+2\.60%\]/)).toBeInTheDocument();
    expect(screen.getByText("above materiality")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /gender \+2\.00%/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("keeps an earlier attribute after its events leave the stream buffer", () => {
    const gender = makeProbe({
      b_running: 40,
      c_running: 0,
      n_running: 2000,
      net_flip_rate_running: 0.02,
      ci_low_running: 0.014,
      ci_high_running: 0.026,
    });
    const view = render(
      <TooltipProvider>
        <EvidenceMeter
          events={[gender]}
          materiality={0.02}
          ciLevel={0.95}
          bootstrapIterations={4000}
        />
      </TooltipProvider>,
    );

    // The stream buffer is capped: only the newest probe's frames remain.
    const pincode = makeProbe({
      probe_id: "single-pincode_group-female",
      changed_field: "pincode_group",
      b_running: 0,
      c_running: 0,
      n_running: 1,
      net_flip_rate_running: 0,
    });
    view.rerender(
      <TooltipProvider>
        <EvidenceMeter
          events={[pincode]}
          materiality={0.02}
          ciLevel={0.95}
          bootstrapIterations={4000}
        />
      </TooltipProvider>,
    );

    const group = screen.getByRole("group", { name: /evidence by attribute/i });
    expect(group).toHaveTextContent("gender +2.00%");
    expect(group).toHaveTextContent("region group +0.00%");
    expect(screen.getByText(/over 1 pairs · region group/)).toBeInTheDocument();
  });
});
