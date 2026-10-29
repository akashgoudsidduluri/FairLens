import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TwinStream } from "@/components/arena/TwinStream";
import { makeProbe } from "@/test/fixtures";

describe("TwinStream", () => {
  it("renders a twin pair with one highlighted field and two decision stamps", () => {
    render(<TwinStream events={[makeProbe()]} />);
    const pair = screen.getByTestId("twin-pair");
    expect(pair).toHaveAttribute("data-flip", "true");
    expect(screen.getAllByText("gender · changed")).toHaveLength(2);
    expect(screen.getAllByText("approved").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("rejected")).toBeInTheDocument();
    expect(screen.getByText("flipped")).toBeInTheDocument();
    expect(screen.getByText(/only gender changed/)).toBeInTheDocument();
  });

  it("highlights the age band when an age probe changes the band", () => {
    render(
      <TwinStream
        events={[
          makeProbe({
            probe_id: "single-age-45plus",
            changed_field: "age",
            original: {
              id: "orig-age",
              income: 420000,
              gender: "male",
              age_band: "<35",
              urban_rural: "urban",
              pincode_group: "P1",
              name_group: "N1",
            },
            twin: {
              id: "twin-age",
              income: 420000,
              gender: "male",
              age_band: "45+",
              urban_rural: "urban",
              pincode_group: "P1",
              name_group: "N1",
            },
          }),
        ]}
      />,
    );
    expect(screen.getAllByText("age band · changed")).toHaveLength(2);
    expect(screen.getByText("changed: age")).toBeInTheDocument();
  });

  it("fades matching pairs after a moment while flips stay readable", () => {
    vi.useFakeTimers();
    render(
      <TwinStream
        events={[makeProbe({ pair_index: 0, twin_approved: true })]}
      />,
    );
    expect(screen.getByText("same decision")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByText("same decision · faded")).toBeInTheDocument();
  });

  it("caps on-screen pairs at five and shows the newest first", () => {
    const events = Array.from({ length: 8 }, (_, index) =>
      makeProbe({
        pair_index: index,
        b_running: index % 2,
        c_running: index % 3,
        twin_approved: index % 2 === 0,
      }),
    );
    render(<TwinStream events={events} />);
    expect(screen.getAllByTestId("twin-pair")).toHaveLength(5);
    expect(screen.getByText("pair #8")).toBeInTheDocument();
    expect(screen.queryByText("pair #3")).not.toBeInTheDocument();
  });
});
