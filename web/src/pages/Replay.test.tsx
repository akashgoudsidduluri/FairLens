import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { Replay } from "@/pages/Replay";
import { makeCatalog, makeMeta, makeRecord, makeReplay } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      meta: vi.fn(),
      getTargets: vi.fn(),
      getReplay: vi.fn(),
      startAudit: vi.fn(),
    },
  };
});

const meta = vi.mocked(api.meta);
const getTargets = vi.mocked(api.getTargets);
const getReplay = vi.mocked(api.getReplay);

function renderReplay() {
  return render(
    <TooltipProvider>
      <MemoryRouter initialEntries={["/replay/sandbox-2-seed-42"]}>
        <Routes>
          <Route path="/replay/:replayId" element={<Replay />} />
        </Routes>
      </MemoryRouter>
    </TooltipProvider>,
  );
}

describe("Replay page", () => {
  beforeEach(() => {
    meta.mockReset();
    getTargets.mockReset();
    getReplay.mockReset();
    meta.mockResolvedValue(makeMeta());
    getTargets.mockResolvedValue(makeCatalog());
    getReplay.mockResolvedValue(makeReplay());
  });

  it("labels the recording and renders playback controls", async () => {
    renderReplay();

    expect(
      (await screen.findAllByText(/Replay of a recorded audit/i)).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/no sandbox or model was contacted/i)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /pause replay/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /restart replay/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/replay position/i)).toBeInTheDocument();
  });

  it("skips to the report and keeps sign-off read-only", async () => {
    const user = userEvent.setup();
    renderReplay();

    await screen.findByRole("button", { name: /skip replay to the report/i });
    expect(
      screen.queryByRole("heading", { name: /what survived the skeptic/i }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /skip replay to the report/i }));

    expect(
      await screen.findByRole("heading", { name: /what survived the skeptic/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/read-only recording/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/approver name/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run again/i })).toBeInTheDocument();
  });

  it("labels a real-data recording by target instead of the legacy model id", async () => {
    getReplay.mockResolvedValue(
      makeReplay({
        id: "adult-income-seed-42",
        label: "UCI Adult (gradient boosting)",
        audit: makeRecord({
          model_id: 2,
          target: "targets/real/adult-income.yaml",
        }),
      }),
    );
    renderReplay();

    expect(
      (await screen.findAllByText("Adult Income")).length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("model 2")).not.toBeInTheDocument();
  });

  it("reports a missing recording without starting an audit", async () => {
    const { ApiError } = await import("@/lib/api");
    getReplay.mockRejectedValue(new ApiError(404, "replay not found"));

    renderReplay();

    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByText("replay not found")).toBeInTheDocument();
    expect(api.startAudit).not.toHaveBeenCalled();
  });
});
