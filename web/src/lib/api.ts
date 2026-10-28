/**
 * Typed client for the FairLens audit service (api/, port 8020).
 *
 * The browser always calls /api/*. Vite proxies that prefix to the service in
 * development (see vite.config.ts); a deployment can serve the built app behind
 * the same reverse proxy. Types come from the generated web/src/api-types.ts.
 */

import type {
  AuditCreateRequest,
  AuditCreated,
  AuditRecord,
  CertificateList,
  DecisionResponse,
  EndpointCheckRequest,
  EndpointCheckResponse,
  HealthResponse,
  TargetCatalog,
  VerifyResponse,
} from "@/api-types";

export const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail || `request failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // Keep the status line when the body is not JSON.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  /** Model Library. Capabilities and availability are authoritative server-side. */
  getTargets: () => request<TargetCatalog>("/targets"),

  /** Server-side health check; auth secrets never leave the API process. */
  checkEndpoint: (body: EndpointCheckRequest) =>
    request<EndpointCheckResponse>("/targets/check", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  startAudit: (body: AuditCreateRequest) =>
    request<AuditCreated>("/audits", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getAudit: (auditId: string) => request<AuditRecord>(`/audits/${auditId}`),

  decide: (auditId: string, approver: string, decision: "approve" | "reject") =>
    request<DecisionResponse>(`/audits/${auditId}/decision`, {
      method: "POST",
      body: JSON.stringify({ approver, decision }),
    }),

  certificates: () => request<CertificateList>("/certificates"),

  verifyCertificates: () =>
    request<VerifyResponse>("/certificates/verify", { method: "POST" }),
};

/**
 * SSE URL. `lastEventId` is sent both as a query parameter (explicit resume the
 * hook controls) and is what the browser sends natively in the Last-Event-ID
 * header on its own reconnects. The API accepts either.
 */
export function streamUrl(auditId: string, lastEventId = 0): string {
  const path = `${API_BASE}/audits/${encodeURIComponent(auditId)}/events`;
  return lastEventId > 0 ? `${path}?last_event_id=${lastEventId}` : path;
}
