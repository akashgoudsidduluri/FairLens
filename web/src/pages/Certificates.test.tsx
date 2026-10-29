import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Certificate } from "@/api-types";
import { api } from "@/lib/api";
import { Certificates } from "@/pages/Certificates";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      certificates: vi.fn(),
      verifyCertificates: vi.fn(),
      tamperCertificate: vi.fn(),
    },
  };
});

const certificates = vi.mocked(api.certificates);
const verifyCertificates = vi.mocked(api.verifyCertificates);
const tamperCertificate = vi.mocked(api.tamperCertificate);

function certificate(overrides: Partial<Certificate> = {}): Certificate {
  return {
    index: 0,
    prev_hash: "0".repeat(64),
    record_hash: "a".repeat(64),
    payload: { approver: "Dr A. Rao", decision: "approve" },
    created_at: "2026-01-01T00:05:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/certificates"]}>
      <Certificates />
    </MemoryRouter>,
  );
}

describe("Certificates page", () => {
  beforeEach(() => {
    certificates.mockReset();
    verifyCertificates.mockReset();
    tamperCertificate.mockReset();
  });

  it("says an empty store is not a verified chain", async () => {
    certificates.mockResolvedValue({ records: [], count: 0 });
    renderPage();

    expect(await screen.findByText("No audit records yet.")).toBeInTheDocument();
    expect(screen.getByText(/not checked · 0 records/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /verify chain/i }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Nothing to verify until a decision is issued/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/chain verified/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /tamper with newest record/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the chain and reports a verified recomputation", async () => {
    const user = userEvent.setup();
    certificates.mockResolvedValue({
      records: [
        certificate(),
        certificate({
          index: 1,
          prev_hash: "a".repeat(64),
          record_hash: "b".repeat(64),
          payload: { approver: "S. Iyer", decision: "reject" },
          created_at: "2026-01-01T00:09:00Z",
        }),
      ],
      count: 2,
    });
    verifyCertificates.mockResolvedValue({
      verified: true,
      first_broken: null,
      records: 2,
    });
    renderPage();

    expect(await screen.findByText("Dr A. Rao")).toBeInTheDocument();
    expect(screen.getByText("S. Iyer")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Audit Record 0")).getByText("genesis")).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Audit Record 0")).getByText("a".repeat(64)),
    ).toBeInTheDocument();
    expect(screen.getByText(/not checked · 2 records/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /verify chain/i }));

    expect(verifyCertificates).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/chain verified · 2 records/)).toBeInTheDocument();
    expect(
      screen.getByText(/2 records recomputed without a break/),
    ).toBeInTheDocument();
  });

  it("marks the first broken record and runs the labelled tamper demo", async () => {
    const user = userEvent.setup();
    certificates.mockResolvedValue({
      records: [
        certificate(),
        certificate({
          index: 1,
          record_hash: "b".repeat(64),
          payload: { approver: "S. Iyer", decision: "approve" },
        }),
      ],
      count: 2,
    });
    verifyCertificates.mockResolvedValue({
      verified: false,
      first_broken: 1,
      records: 2,
    });
    const broken = { verified: false, first_broken: 1, records: 2 };
    tamperCertificate.mockResolvedValue({
      index: 1,
      field: "payload",
      before: { approver: "Dr A. Rao", decision: "approve" },
      after: { approver: "Tampered Demo Record", decision: "reject" },
      verification: broken,
    });
    renderPage();

    await screen.findByText("Dr A. Rao");
    await user.click(screen.getByRole("button", { name: /verify chain/i }));

    expect(await screen.findByText(/chain broken · 2 records/)).toBeInTheDocument();
    expect(
      screen.getByText(/First break at record #1/),
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Audit Record 1")).getByText(
        /first broken record/,
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Audit Record 0")).queryByText(
        /first broken record/,
      ),
    ).not.toBeInTheDocument();

    const tamper = screen.getByRole("button", {
      name: /tamper with newest record/i,
    });
    expect(tamper).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", { name: /I understand this writes/i }),
    );
    expect(tamper).toBeEnabled();
    await user.click(tamper);

    expect(tamperCertificate).toHaveBeenCalledWith(1);
    // The page reloads the store after tampering, and the chain stays broken.
    expect(await screen.findByText(/chain broken · 2 records/)).toBeInTheDocument();
  });
});
