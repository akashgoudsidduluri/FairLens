import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Landing } from "@/pages/Landing";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, api } from "@/lib/api";
import { makeCatalog } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getTargets: vi.fn(),
      getReplays: vi.fn(),
      startAudit: vi.fn(),
      checkEndpoint: vi.fn(),
    },
  };
});

const getTargets = vi.mocked(api.getTargets);
const getReplays = vi.mocked(api.getReplays);
const startAudit = vi.mocked(api.startAudit);

function renderLanding() {
  return render(
    <TooltipProvider>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/audit/:auditId" element={<div>arena {":auditId"}</div>} />
        </Routes>
      </MemoryRouter>
    </TooltipProvider>,
  );
}

describe("Landing Model Library", () => {
  beforeEach(() => {
    getTargets.mockReset();
    getReplays.mockReset();
    getReplays.mockResolvedValue({ replays: [], count: 0 });
    startAudit.mockReset();
  });

  it("groups both validation suites, two real models, and the LLM screener", async () => {
    getTargets.mockResolvedValue(makeCatalog());
    renderLanding();

    expect(await screen.findByText("Validation model 1")).toBeInTheDocument();
    expect(screen.getByText("Validation model 7")).toBeInTheDocument();
    expect(screen.getByText("Validation model 8")).toBeInTheDocument();
    expect(screen.getByText("Control model 15")).toBeInTheDocument();
    expect(screen.getByText("Adult Income")).toBeInTheDocument();
    expect(screen.getByText("UCI Credit Default")).toBeInTheDocument();
    const library = within(document.getElementById("model-library") as HTMLElement);
    expect(library.getAllByText("LLM screener")).toHaveLength(2);

    expect(screen.getAllByText("validation suite")).toHaveLength(15);
    expect(screen.getAllByText("real model")).toHaveLength(2);
    expect(screen.getByText("unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("configured")).toHaveLength(15);
    expect(
      screen.getByText("validation suite B · model 1/7"),
    ).toBeInTheDocument();
    expect(screen.getByText("validation suite B · control B")).toBeInTheDocument();
  });

  it("keeps Start Audit disabled only for the unavailable LLM target", async () => {
    getTargets.mockResolvedValue(makeCatalog());
    renderLanding();
    await screen.findByText("Validation model 1");

    const library = within(document.getElementById("model-library") as HTMLElement);
    const buttons = library.getAllByRole("button", { name: /start audit/i });
    expect(buttons).toHaveLength(18);
    expect(buttons.filter((button) => button.hasAttribute("disabled"))).toHaveLength(1);
  });

  it("starts a validation audit and navigates to the arena", async () => {
    const user = userEvent.setup();
    getTargets.mockResolvedValue(makeCatalog());
    startAudit.mockResolvedValue({
      id: "run1",
      events_url: "/audits/run1/events",
      result_url: "/audits/run1",
    });
    renderLanding();
    await screen.findByText("Validation model 1");

    await user.click(
      within(document.getElementById("model-library") as HTMLElement).getAllByRole(
        "button",
        { name: /start audit/i },
      )[0],
    );
    expect(startAudit).toHaveBeenCalledWith({
      model_id: 1,
      target: "sandbox:1",
      include_mitigation: false,
      include_narrative: true,
    });
    await waitFor(() =>
      expect(screen.getByText(/arena/)).toBeInTheDocument(),
    );
  });

  it("links to committed recordings without starting an audit", async () => {
    getTargets.mockResolvedValue(makeCatalog());
    getReplays.mockResolvedValue({
      count: 2,
      replays: [
        {
          id: "sandbox-2-seed-42",
          label: "Validation model 2",
          model_id: 2,
          seed: 42,
          duration_ms: 88000,
        },
        {
          id: "adult-income-seed-42",
          label: "Adult Income",
          model_id: 0,
          seed: 42,
          duration_ms: 600000,
        },
      ],
    });
    renderLanding();

    const replayLink = await screen.findByRole("link", {
      name: /validation model 2/i,
    });
    expect(replayLink).toHaveAttribute("href", "/replay/sandbox-2-seed-42");
    expect(screen.getByText("2 recordings")).toBeInTheDocument();
    expect(
      screen.getByText(/model 2 · seed 42 · 1m 28s/i),
    ).toBeInTheDocument();
    expect(startAudit).not.toHaveBeenCalled();
  });

  it("says when the service returns an empty catalog instead of showing blank sections", async () => {
    getTargets.mockResolvedValue({ targets: [] });
    renderLanding();

    expect(
      await screen.findByText(/No targets were returned/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Validation suite/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reload targets/i }),
    ).toBeInTheDocument();
  });

  it("shows an offline state with a retry when the service is down", async () => {
    getTargets.mockRejectedValue(new ApiError(503, "service unavailable"));
    renderLanding();
    expect(
      await screen.findByText(/The audit service is not answering/),
    ).toBeInTheDocument();
    expect(screen.getByText(/service unavailable/)).toBeInTheDocument();

    getTargets.mockResolvedValue(makeCatalog());
    await userEvent.setup().click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Validation model 1")).toBeInTheDocument();
  });
});
