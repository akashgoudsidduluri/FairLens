import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConnectEndpoint } from "@/components/library/ConnectEndpoint";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      checkEndpoint: vi.fn(),
      startAudit: vi.fn(),
    },
  };
});

const checkEndpoint = vi.mocked(api.checkEndpoint);
const startAudit = vi.mocked(api.startAudit);

describe("ConnectEndpoint", () => {
  beforeEach(() => {
    checkEndpoint.mockReset();
    startAudit.mockReset();
  });

  it("gates Start Audit behind a successful health check", async () => {
    const user = userEvent.setup();
    const onStarted = vi.fn();
    render(<ConnectEndpoint onStarted={onStarted} />);

    const start = screen.getByRole("button", { name: /start audit/i });
    expect(start).toBeDisabled();

    await user.type(
      screen.getByLabelText("Endpoint URL"),
      "https://lender.test/",
    );
    checkEndpoint.mockResolvedValue({
      ok: true,
      status_code: 200,
      detail: "endpoint answered the health check",
      latency_ms: 42,
      models: ["credit"],
    });

    await user.click(screen.getByRole("button", { name: /check endpoint/i }));
    expect(checkEndpoint).toHaveBeenCalledWith({
      base_url: "https://lender.test/",
      health_path: "/health",
      auth_env_var: null,
      auth_header: "X-API-Key",
      probe_cap: 5000,
    });
    await screen.findByText(/endpoint answered the health check/);
    expect(start).toBeEnabled();

    startAudit.mockResolvedValue({
      id: "abc123",
      events_url: "/audits/abc123/events",
      result_url: "/audits/abc123",
    });
    await user.click(start);

    expect(startAudit).toHaveBeenCalledTimes(1);
    const body = startAudit.mock.calls[0][0];
    expect(body.model_id).toBe(1);
    expect(body.include_mitigation).toBe(false);
    const spec = body.target_spec as Record<string, unknown>;
    expect(spec.base_url).toBe("https://lender.test");
    expect(spec.auth).toEqual({ type: "none" });
    expect(spec.response).toMatchObject({
      items: "$",
      approved: "approved",
      score: "score",
    });
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith("abc123"));
  });

  it("keeps Start Audit locked when the health check fails", async () => {
    const user = userEvent.setup();
    render(<ConnectEndpoint onStarted={vi.fn()} />);
    await user.type(screen.getByLabelText("Endpoint URL"), "https://lender.test");
    checkEndpoint.mockResolvedValue({
      ok: false,
      status_code: 503,
      detail: "health check returned HTTP 503",
      latency_ms: 12,
    });

    await user.click(screen.getByRole("button", { name: /check endpoint/i }));
    await screen.findByText(/health check returned HTTP 503/);
    expect(screen.getByRole("button", { name: /start audit/i })).toBeDisabled();
    expect(screen.getByText(/run the health check to unlock/i)).toBeInTheDocument();
  });

  it("re-locks Start Audit when the form changes after a pass", async () => {
    const user = userEvent.setup();
    render(<ConnectEndpoint onStarted={vi.fn()} />);
    await user.type(screen.getByLabelText("Endpoint URL"), "https://lender.test");
    checkEndpoint.mockResolvedValue({
      ok: true,
      detail: "endpoint answered the health check",
      latency_ms: 10,
      models: [],
    });
    await user.click(screen.getByRole("button", { name: /check endpoint/i }));
    await screen.findByText(/endpoint answered the health check/);
    expect(screen.getByRole("button", { name: /start audit/i })).toBeEnabled();

    await user.type(screen.getByLabelText("Score path"), "/v2/score");
    expect(screen.getByRole("button", { name: /start audit/i })).toBeDisabled();
  });

  it("sends an auth env var name without ever handling the secret", async () => {
    const user = userEvent.setup();
    render(<ConnectEndpoint onStarted={vi.fn()} />);
    await user.type(screen.getByLabelText("Endpoint URL"), "https://lender.test");
    await user.type(screen.getByLabelText(/Auth env var name/), "LENDER_KEY");
    checkEndpoint.mockResolvedValue({
      ok: true,
      detail: "endpoint answered the health check",
      latency_ms: 10,
      models: [],
    });
    await user.click(screen.getByRole("button", { name: /check endpoint/i }));
    await screen.findByText(/endpoint answered the health check/);

    startAudit.mockResolvedValue({
      id: "x",
      events_url: "/audits/x/events",
      result_url: "/audits/x",
    });
    await user.click(screen.getByRole("button", { name: /start audit/i }));
    const spec = startAudit.mock.calls[0][0].target_spec as Record<string, unknown>;
    expect(spec.auth).toEqual({
      type: "header",
      header_name: "X-API-Key",
      token_env: "LENDER_KEY",
    });
    expect(JSON.stringify(spec)).not.toContain("secret");
  });
});
