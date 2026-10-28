import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditRecord } from "@/api-types";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuditStream } from "@/hooks/useAuditStream";
import { api } from "@/lib/api";
import { Arena } from "@/pages/Arena";
import { makeAgent, makeCatalog, makeMeta, makeProbe } from "@/test/fixtures";

vi.mock("@/hooks/useAuditStream", () => ({
  useAuditStream: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, meta: vi.fn(), getAudit: vi.fn(), getTargets: vi.fn() },
  };
});

const mockedStream = vi.mocked(useAuditStream);
const meta = vi.mocked(api.meta);
const getAudit = vi.mocked(api.getAudit);
const getTargets = vi.mocked(api.getTargets);

function record(): AuditRecord {
  return {
    id: "run1",
    status: "running",
    model_id: 2,
    target: "sandbox:2",
    api_url: "http://127.0.0.1:8010",
    seed: 42,
    include_mitigation: false,
    include_narrative: true,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function renderArena() {
  return render(
    <TooltipProvider>
      <MemoryRouter initialEntries={["/audit/run1"]}>
        <Routes>
          <Route path="/audit/:auditId" element={<Arena />} />
        </Routes>
      </MemoryRouter>
    </TooltipProvider>,
  );
}

describe("Arena page", () => {
  beforeEach(() => {
    meta.mockReset();
    getAudit.mockReset();
    getTargets.mockReset();
    meta.mockResolvedValue(makeMeta());
    getAudit.mockResolvedValue(record());
    getTargets.mockResolvedValue(makeCatalog());
  });

  it("wires the stream, evidence, lanes, tray, and early stop together", async () => {
    const events = [
      makeProbe({
        pair_index: 0,
        b_running: 1,
        c_running: 0,
        n_running: 1,
        net_flip_rate_running: 1,
      }),
      makeProbe({
        pair_index: 1,
        b_running: 1,
        c_running: 1,
        n_running: 2,
        net_flip_rate_running: 0,
        twin_approved: true,
      }),
    ];
    mockedStream.mockReturnValue({
      status: "open",
      agentEvents: [
        makeAgent({ agent: "planner", message: "planning probes" }),
        makeAgent({
          agent: "statistician",
          message: "Sequential stop for gender",
          payload: {
            attribute: "gender",
            n: 1200,
            requested_n: 2000,
            stop_reason: "stop_material_harm",
          },
        }),
        makeAgent({ agent: "skeptic", message: "challenging the finding" }),
      ],
      probeEvents: events,
      probeCount: 2,
      lastEventId: 7,
      reconnects: 0,
      error: null,
      done: null,
    });

    renderArena();

    expect(await screen.findByText("Validation model 2")).toBeInTheDocument();
    expect(screen.getByText(/Stopped early on gender/)).toBeInTheDocument();
    expect(screen.getAllByTestId("twin-pair")).toHaveLength(2);
    expect(await screen.findByText("1 kept")).toBeInTheDocument();
    expect(screen.getByText("challenging the finding")).toBeInTheDocument();
    expect(screen.getByText("event #7")).toBeInTheDocument();
  });

  it("shows the completion banner and finding count", async () => {
    mockedStream.mockReturnValue({
      status: "done",
      agentEvents: [makeAgent({ agent: "reporter", message: "report ready" })],
      probeEvents: [makeProbe()],
      probeCount: 1,
      lastEventId: 12,
      reconnects: 1,
      error: null,
      done: { audit_id: "run1", status: "completed", last_seq: 12 },
    });
    getAudit.mockResolvedValue({
      ...record(),
      status: "completed",
      result: {
        model_id: 2,
        config: {},
        findings: [],
        narrative: "No finding survived the Skeptic.",
      },
    });

    renderArena();

    expect(await screen.findByText(/Audit complete/)).toBeInTheDocument();
    expect(screen.getByText(/0 findings in the report/)).toBeInTheDocument();
    expect(screen.getByText(/report ready/)).toBeInTheDocument();
    expect(screen.getByText("resumed 1×")).toBeInTheDocument();
  });

  it("uses the stored probe cap for a connected endpoint after a reload", async () => {
    mockedStream.mockReturnValue({
      status: "open",
      agentEvents: [],
      probeEvents: [makeProbe()],
      probeCount: 10,
      lastEventId: 4,
      reconnects: 0,
      error: null,
      done: null,
    });
    // The inline target is not in the catalog, so the record is the only place
    // the stricter cap can come from after the arena is reloaded.
    getAudit.mockResolvedValue({
      ...record(),
      target: "inline:connected-endpoint",
      probe_cap: 5000,
    });

    renderArena();

    expect(await screen.findByText(/\/ 5,000 applicants/)).toBeInTheDocument();
    expect(screen.queryByText(/\/ 100,000 applicants/)).not.toBeInTheDocument();
  });

  it("keeps the meter off when thresholds cannot be read", async () => {
    meta.mockRejectedValue(new Error("offline"));
    mockedStream.mockReturnValue({
      status: "connecting",
      agentEvents: [],
      probeEvents: [],
      probeCount: 0,
      lastEventId: 0,
      reconnects: 0,
      error: null,
      done: null,
    });

    renderArena();

    expect(
      await screen.findByText(/Pre-registered thresholds are unavailable/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(screen.queryByText("above materiality")).not.toBeInTheDocument();
  });
});
