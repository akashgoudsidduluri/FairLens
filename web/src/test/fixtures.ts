import type {
  AgentEvent,
  AuditRecord,
  AuditReport,
  Finding,
  ProbeEvent,
  ReplayFile,
  ServiceMeta,
  StreamEvent,
  TargetCard,
  TargetCatalog,
} from "@/api-types";

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
      label: "UCI Credit Default",
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

export function makeProbe(overrides: Partial<ProbeEvent> = {}): ProbeEvent {
  const pairIndex = overrides.pair_index ?? 0;
  const b = overrides.b_running ?? pairIndex;
  const c = overrides.c_running ?? 0;
  const n = overrides.n_running ?? pairIndex + 1;
  return {
    probe_id: "single-gender-female",
    phase: "single_attribute",
    pair_index: pairIndex,
    changed_field: "gender",
    original: {
      id: `orig-${pairIndex}`,
      income: 420000,
      gender: "male",
      age_band: "35-44",
      urban_rural: "urban",
      pincode_group: "P1",
      name_group: "N1",
    },
    twin: {
      id: `twin-${pairIndex}`,
      income: 420000,
      gender: "female",
      age_band: "35-44",
      urban_rural: "urban",
      pincode_group: "P1",
      name_group: "N1",
    },
    original_approved: true,
    twin_approved: false,
    b_running: b,
    c_running: c,
    n_running: n,
    net_flip_rate_running: (b - c) / n,
    ci_low_running: 0,
    ci_high_running: 0.1,
    ci_method: "normal_approximation",
    timestamp: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export function makeAgent(overrides: Partial<AgentEvent> = {}): AgentEvent {
  return {
    agent: "planner",
    message: "Audit plan ready.",
    payload: {},
    timestamp: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export function makeFinding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: "single-gender-female",
    kind: "single_attribute",
    attribute_or_subgroup: "gender=female",
    target_group: "female",
    comparison_group: "male",
    evidence: {
      n: 2000,
      b: 1307,
      c: 0,
      net_flip_rate: 0.6535,
      ci_low: 0.633,
      ci_high: 0.6735,
      p_raw: 0,
      p_adjusted: 0,
    },
    observational_gap: 0.52,
    observational_rates: { female: 0.18, male: 0.7 },
    status: "kept",
    reason: "Kept: the effect persists in the income-matched re-test.",
    matched_evidence: null,
    ...overrides,
  };
}

export function makeReport(overrides: Partial<AuditReport> = {}): AuditReport {
  return {
    model_id: 2,
    config: {},
    findings: [makeFinding()],
    impact: [],
    mitigation_curve: [],
    narrative: "",
    number_check_result: {},
    observational: {},
    ...overrides,
  };
}


export function makeMeta(overrides: Partial<ServiceMeta> = {}): ServiceMeta {
  return {
    materiality: 0.02,
    alpha: 0.05,
    ci_level: 0.95,
    bootstrap_iterations: 4000,
    n_pairs: 2000,
    probe_cap: 100000,
    sequential_enabled: false,
    sequential_min_pairs: 1000,
    sequential_check_every: 200,
    ...overrides,
  };
}

export function makeRecord(overrides: Partial<AuditRecord> = {}): AuditRecord {
  return {
    id: "source-audit",
    status: "completed",
    model_id: 2,
    target: "sandbox:2",
    api_url: "http://127.0.0.1:8010",
    seed: 42,
    include_mitigation: false,
    include_narrative: false,
    created_at: "2026-01-01T00:00:00Z",
    started_at: "2026-01-01T00:00:00Z",
    completed_at: "2026-01-01T00:00:10Z",
    result: makeReport({ findings: [], narrative: "" }),
    ...overrides,
  };
}

export function makeReplay(overrides: Partial<ReplayFile> = {}): ReplayFile {
  const events: StreamEvent[] = [
    { seq: 1, kind: "agent", data: makeAgent({ message: "plan" }) },
    { seq: 2, kind: "probe", data: makeProbe({ pair_index: 0 }) },
    { seq: 3, kind: "agent", data: makeAgent({ message: "testing" }) },
    { seq: 4, kind: "probe", data: makeProbe({ pair_index: 1 }) },
    { seq: 5, kind: "probe", data: makeProbe({ pair_index: 2 }) },
  ];
  return {
    version: 1,
    id: "sandbox-2-seed-42",
    label: "Validation model 2",
    recorded_at: "2026-01-01T00:00:10Z",
    source_audit_id: "source-audit",
    audit: makeRecord(),
    events,
    ...overrides,
  };
}
