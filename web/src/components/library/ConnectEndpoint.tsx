import * as React from "react";
import { Activity, ArrowRight, Loader2, PlugZap, ShieldCheck } from "lucide-react";

import type { EndpointCheckResponse } from "@/api-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface ConnectForm {
  baseUrl: string;
  authEnvVar: string;
  healthPath: string;
  requestPath: string;
  responseItems: string;
  approvedField: string;
  scoreField: string;
  probeCap: string;
}

export const DEFAULT_FORM: ConnectForm = {
  baseUrl: "",
  authEnvVar: "",
  healthPath: "/health",
  requestPath: "/score_batch",
  responseItems: "$",
  approvedField: "approved",
  scoreField: "score",
  probeCap: "5000",
};

/** Build the inline adapter spec sent to POST /audits. */
export function buildTargetSpec(form: ConnectForm): Record<string, unknown> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const authEnvVar = form.authEnvVar.trim();
  return {
    name: "connected-endpoint",
    base_url: form.baseUrl.trim().replace(/\/+$/, ""),
    health: { path: form.healthPath.trim() || "/health" },
    request: {
      method: "POST",
      path: form.requestPath.trim() || "/score_batch",
      headers,
      body: "${applicants}",
    },
    response: {
      items: form.responseItems.trim() || "$",
      approved: form.approvedField.trim() || "approved",
      score: form.scoreField.trim() || "score",
    },
    limits: {
      probe_cap: Number(form.probeCap) || 0,
      max_retries: 2,
      backoff_seconds: 0.25,
      timeout_seconds: 20,
    },
    auth: authEnvVar
      ? { type: "header", header_name: "X-API-Key", token_env: authEnvVar }
      : { type: "none" },
  };
}

export interface ConnectEndpointProps {
  onStarted: (auditId: string) => void;
}

export function ConnectEndpoint({ onStarted }: ConnectEndpointProps) {
  const [form, setForm] = React.useState<ConnectForm>(DEFAULT_FORM);
  const [checking, setChecking] = React.useState(false);
  const [starting, setStarting] = React.useState(false);
  const [check, setCheck] = React.useState<EndpointCheckResponse | null>(null);
  const [checkedSignature, setCheckedSignature] = React.useState<string | null>(
    null,
  );
  const [error, setError] = React.useState<string | null>(null);

  const signature = JSON.stringify(form);
  const verified = Boolean(check?.ok) && checkedSignature === signature;

  const update = (key: keyof ConnectForm) => (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const value = event.target.value;
    setForm((previous) => ({ ...previous, [key]: value }));
    setCheck(null);
    setCheckedSignature(null);
    setError(null);
  };

  const runCheck = async () => {
    setChecking(true);
    setError(null);
    setCheck(null);
    setCheckedSignature(null);
    try {
      const probeCap = Number(form.probeCap);
      const result = await api.checkEndpoint({
        base_url: form.baseUrl.trim(),
        health_path: form.healthPath.trim() || "/health",
        auth_env_var: form.authEnvVar.trim() || null,
        auth_header: "X-API-Key",
        probe_cap:
          Number.isFinite(probeCap) && probeCap > 0 ? Math.trunc(probeCap) : 5000,
      });
      setCheck(result);
      if (result.ok) setCheckedSignature(signature);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "health check failed");
    } finally {
      setChecking(false);
    }
  };

  const start = async () => {
    if (!verified) return;
    setStarting(true);
    setError(null);
    try {
      const created = await api.startAudit({
        model_id: 1,
        target_spec: buildTargetSpec(form),
        include_mitigation: false,
        include_narrative: true,
      });
      onStarted(created.id);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : "could not start audit");
    } finally {
      setStarting(false);
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-2 border-b border-line/60 bg-raised/30">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <PlugZap className="h-4 w-4 text-accent" aria-hidden="true" />
            <CardTitle>Connect your endpoint</CardTitle>
          </div>
          <Badge variant="outline">bring your own model</Badge>
        </div>
        <CardDescription>
          Point FairLens at a black-box decision API. We health-check it from the
          server before Start Audit unlocks, then send twin applicants.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-5">
        <div className="grid gap-4 md:grid-cols-2">
          <Field
            id="baseUrl"
            label="Endpoint URL"
            value={form.baseUrl}
            onChange={update("baseUrl")}
            placeholder="https://lender.example/api"
            hint="http:// or https:// only. No credentials in the URL."
          />
          <Field
            id="authEnvVar"
            label="Auth env var name (optional)"
            value={form.authEnvVar}
            onChange={update("authEnvVar")}
            placeholder="LENDER_API_KEY"
            hint="The secret stays on the API server. We only store this variable name."
          />
        </div>

        <div className="rounded-lg border border-line/70 bg-canvas/40 p-3">
          <p className="eyebrow">field mapping</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field
              id="requestPath"
              label="Score path"
              value={form.requestPath}
              onChange={update("requestPath")}
              placeholder="/score_batch"
              compact
            />
            <Field
              id="responseItems"
              label="Response list"
              value={form.responseItems}
              onChange={update("responseItems")}
              placeholder="$"
              compact
            />
            <Field
              id="approvedField"
              label="Decision field"
              value={form.approvedField}
              onChange={update("approvedField")}
              placeholder="approved"
              compact
            />
            <Field
              id="scoreField"
              label="Score field (optional)"
              value={form.scoreField}
              onChange={update("scoreField")}
              placeholder="score"
              compact
            />
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-muted/80">
            We POST the applicant list to the score path and read a decision per
            applicant. Use <span className="font-mono text-muted">$</span> for the
            whole response body.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            id="healthPath"
            label="Health path"
            value={form.healthPath}
            onChange={update("healthPath")}
            placeholder="/health"
            compact
            hint="Must answer HTTP 200 from the API server."
          />
          <Field
            id="probeCap"
            label="Probe cap (applicants)"
            value={form.probeCap}
            onChange={update("probeCap")}
            placeholder="5000"
            type="number"
            compact
            hint="A hard ceiling. The audit fails rather than exceed it."
          />
        </div>

        {check && (
          <div
            role="status"
            className={cn(
              "flex items-start gap-2 rounded-lg border px-3 py-2 text-[12px]",
              check.ok
                ? "border-ok/30 bg-ok/[0.06] text-ok"
                : "border-danger/30 bg-danger/[0.06] text-danger",
            )}
          >
            {check.ok ? (
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <Activity className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            )}
            <span>
              {check.detail}
              {check.ok && ` · ${check.latency_ms.toFixed(0)} ms`}
              {check.ok && check.models && check.models.length > 0
                ? ` · models: ${check.models.join(", ")}`
                : ""}
            </span>
          </div>
        )}

        {error && (
          <p role="alert" className="text-[12px] text-danger">
            {error}
          </p>
        )}

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            variant="secondary"
            onClick={runCheck}
            disabled={checking || !form.baseUrl.trim()}
          >
            {checking ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Activity className="h-4 w-4" aria-hidden="true" />
            )}
            {checking ? "checking…" : "Check endpoint"}
          </Button>
          <Button
            onClick={start}
            disabled={!verified || starting}
            className="sm:min-w-[180px]"
          >
            {starting ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            )}
            Start audit
          </Button>
          <p className="self-center text-[11px] text-muted">
            {verified
              ? "Health check passed. Start Audit is unlocked."
              : "Run the health check to unlock Start Audit."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
  hint,
  type = "text",
  compact = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  hint?: string;
  type?: string;
  compact?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className={compact ? "h-9 text-[13px]" : undefined}
        min={type === "number" ? 0 : undefined}
        inputMode={type === "number" ? "numeric" : undefined}
      />
      {hint && <p className="text-[10.5px] leading-snug text-muted/75">{hint}</p>}
    </div>
  );
}
