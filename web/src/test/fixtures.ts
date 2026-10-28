import type { TargetCard, TargetCatalog } from "@/api-types";

function baseCard(overrides: Partial<TargetCard>): TargetCard {
  return {
    id: "card",
    label: "Card",
    kind: "validation",
    family: "sandbox",
    target: "sandbox:1",
    model_id: 1,
    description: "A target.",
    supported_probes: ["gender", "pincode_group", "name_group", "intersectional"],
    unsupported_probes: {},
    availability: { status: "configured", reason: "" },
    planned_pairs: 2000,
    probe_cap: 100000,
    metric: null,
    ...overrides,
  };
}

export function makeCatalog(): TargetCatalog {
  const validation = Array.from({ length: 7 }, (_, index) =>
    baseCard({
      id: `sandbox-${index + 1}`,
      label: `Validation model ${index + 1}`,
      target: `sandbox:${index + 1}`,
      model_id: index + 1,
    }),
  );
  const real: TargetCard[] = [
    baseCard({
      id: "uci_credit_default",
      label: "Uci Credit Default",
      kind: "real",
      family: "real",
      target: "targets/real/uci-credit-default.yaml",
      model_id: 1,
      description: "Logistic regression on UCI credit default.",
      supported_probes: ["gender"],
      unsupported_probes: {
        pincode_group: "Dataset has no pincode column.",
        name_group: "Dataset has no name column.",
        intersectional: "No urban/rural column.",
      },
      availability: { status: "available", reason: "" },
    }),
    baseCard({
      id: "adult_income",
      label: "Adult Income",
      kind: "real",
      family: "real",
      target: "targets/real/adult-income.yaml",
      model_id: 2,
      description: "Gradient boosting on UCI Adult Income.",
      supported_probes: ["gender"],
      unsupported_probes: {
        pincode_group: "Dataset has no pincode column.",
        name_group: "Dataset has no name column.",
        intersectional: "No urban/rural column.",
      },
      availability: { status: "available", reason: "" },
    }),
  ];
  const llm = baseCard({
    id: "llm-screener",
    label: "LLM screener",
    kind: "llm",
    family: "llm",
    target: "llm:screener",
    model_id: 1,
    description: "An Anthropic model screens each applicant.",
    supported_probes: ["name_group", "pincode_group"],
    unsupported_probes: {
      gender: "Gender is held fixed in every prompt.",
      intersectional: "No urban/rural input.",
    },
    availability: {
      status: "unavailable",
      reason: "ANTHROPIC_MODEL and ANTHROPIC_API_KEY are not set",
    },
    planned_pairs: 24,
    probe_cap: 300,
  });
  return { targets: [...validation, ...real, llm], service: "fairlens-api" };
}
