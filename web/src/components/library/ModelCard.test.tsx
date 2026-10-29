import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { ModelCard } from "@/components/library/ModelCard";
import { makeCatalog } from "@/test/fixtures";

const cards = makeCatalog().targets;
const realCard = cards.find((card) => card.kind === "real")!;
const llmCard = cards.find((card) => card.kind === "llm")!;

function renderCard(card = cards[0], onStart = vi.fn()) {
  render(
    <TooltipProvider>
      <ModelCard card={card} onStart={onStart} />
    </TooltipProvider>,
  );
  return onStart;
}

describe("ModelCard", () => {
  it("shows what the target can and cannot test, with unsupported reasons", () => {
    renderCard(cards[0]);
    expect(screen.getByText("Validation model 1")).toBeInTheDocument();
    expect(screen.getByText("validation suite")).toBeInTheDocument();
    expect(screen.getByText("configured")).toBeInTheDocument();
    expect(screen.getByLabelText("Supported probes")).toHaveTextContent(
      "gender",
    );
    expect(screen.getByText("Nothing is ruled out for this target.")).toBeInTheDocument();
  });

  it("lists unsupported probes for a real model", () => {
    renderCard(realCard);
    expect(screen.getByText("real model")).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
    const unsupported = screen.getByLabelText("Unsupported probes");
    expect(unsupported).toHaveTextContent("region group");
    expect(unsupported).toHaveTextContent("name group");
    expect(unsupported).toHaveTextContent("combined attributes");
  });

  it("disables Start Audit for an unavailable LLM screener and explains why", () => {
    renderCard(llmCard);
    const start = screen.getByRole("button", { name: /start audit/i });
    expect(start).toBeDisabled();
    expect(screen.getByText("unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(/ANTHROPIC_MODEL and ANTHROPIC_API_KEY are not set/),
    ).toBeInTheDocument();
  });

  it("calls onStart for an available target", async () => {
    const user = userEvent.setup();
    const onStart = renderCard(cards[1]);
    await user.click(screen.getByRole("button", { name: /start audit/i }));
    expect(onStart).toHaveBeenCalledWith(cards[1]);
  });
});
