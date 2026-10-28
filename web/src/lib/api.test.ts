import { describe, expect, it, vi } from "vitest";

import { ApiError, api, streamUrl } from "@/lib/api";

describe("typed API client", () => {
  it("posts a typed audit request and returns the created job", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "abc",
        events_url: "/audits/abc/events",
        result_url: "/audits/abc",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const created = await api.startAudit({
      model_id: 2,
      target: "sandbox:2",
      include_mitigation: false,
    });

    expect(created.id).toBe("abc");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/audits");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      model_id: 2,
      target: "sandbox:2",
      include_mitigation: false,
    });
  });

  it("surfaces the API detail string on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        json: async () => ({ detail: "invalid target: nope" }),
      }),
    );

    await expect(api.getAudit("x")).rejects.toBeInstanceOf(ApiError);
    await expect(api.getAudit("x")).rejects.toThrow("invalid target: nope");
  });

  it("builds the SSE URL and resumes from a sequence", () => {
    expect(streamUrl("a b", 0)).toBe("/api/audits/a%20b/events");
    expect(streamUrl("abc", 42)).toBe("/api/audits/abc/events?last_event_id=42");
  });
});
