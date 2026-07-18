import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchForecastApi } from "./backend-api";
import type { CampaignRow } from "./types";

const rows: CampaignRow[] = [
  {
    date: "2026-07-17",
    channel: "Google Ads",
    campaign_type: "Search",
    campaign_name: "Brand",
    spend: 100,
    clicks: 10,
    impressions: 1000,
    conversions: 2,
    revenue: 400,
    roas: 4,
  },
];

afterEach(() => vi.unstubAllGlobals());

describe("backend request lifecycle", () => {
  it("shares identical in-flight requests while canceling a stale consumer", async () => {
    let resolveResponse!: (response: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveResponse = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const stale = new AbortController();
    const current = new AbortController();

    const staleRequest = fetchForecastApi(rows, 60, "overall", undefined, {
      signal: stale.signal,
    });
    const currentRequest = fetchForecastApi(rows, 60, "overall", undefined, {
      signal: current.signal,
    });
    stale.abort();
    resolveResponse(
      new Response(JSON.stringify({ summary: { horizonDays: 60 } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(staleRequest).rejects.toMatchObject({ name: "AbortError" });
    await expect(currentRequest).resolves.toMatchObject({ summary: { horizonDays: 60 } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
