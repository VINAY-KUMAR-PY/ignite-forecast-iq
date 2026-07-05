import { describe, expect, it } from "vitest";
import {
  aggregateDaily,
  filterRows,
  forecastRevenue,
  simulateChannelForecast,
} from "./forecasting";
import type { CampaignRow } from "./types";

const rows: CampaignRow[] = Array.from({ length: 12 }, (_, day) => {
  const date = `2026-01-${String(day + 1).padStart(2, "0")}`;
  return {
    date,
    channel: day % 2 === 0 ? "Google Ads" : "Meta Ads",
    campaign_type: day % 2 === 0 ? "Search" : "Paid Social",
    campaign_name: day % 2 === 0 ? "Brand Search" : "Prospecting",
    spend: 100 + day * 2,
    clicks: 20 + day,
    impressions: 1000 + day * 10,
    conversions: 4 + day / 10,
    revenue: 400 + day * 12,
    roas: (400 + day * 12) / (100 + day * 2),
  };
});

describe("forecasting business logic", () => {
  it("aggregates duplicate dates and computes blended ROAS", () => {
    const daily = aggregateDaily([
      rows[1],
      rows[0],
      { ...rows[0], spend: 50, revenue: 250, clicks: 5, impressions: 100, conversions: 1 },
    ]);

    expect(daily.map((item) => item.date)).toEqual(["2026-01-01", "2026-01-02"]);
    expect(daily[0]).toMatchObject({ spend: 150, revenue: 650, clicks: 25 });
    expect(daily[0].roas).toBeCloseTo(650 / 150);
  });

  it("filters by segment level without mutating the original rows", () => {
    const filtered = filterRows(rows, { level: "campaign_type", value: "Search" });

    expect(filtered).toHaveLength(6);
    expect(filtered.every((row) => row.campaign_type === "Search")).toBe(true);
    expect(rows).toHaveLength(12);
  });

  it("uses the mean-projection fallback when history is too short", () => {
    const forecast = forecastRevenue(rows.slice(0, 4), 3);
    const historical = forecast.filter((point) => point.historical);
    const future = forecast.filter((point) => !point.historical);

    expect(historical).toHaveLength(4);
    expect(future).toHaveLength(3);
    expect(future[0].lower).toBeLessThan(future[0].value);
    expect(future[0].upper).toBeGreaterThan(future[0].value);
  });

  it("keeps budget simulator outputs finite for sparse channel history", () => {
    const result = simulateChannelForecast(rows, "Google Ads", 150, 30);

    expect(result.channel).toBe("Google Ads");
    expect(result.projectedRevenue).toBeGreaterThan(0);
    expect(Number.isFinite(result.projectedRoas)).toBe(true);
    expect(result.projectedRevenueLower).toBeLessThanOrEqual(result.projectedRevenueUpper);
  });
});
