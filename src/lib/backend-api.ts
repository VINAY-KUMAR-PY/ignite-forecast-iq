import type { CampaignRow, ForecastPoint, ValidationResult } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface ForecastApiResponse {
  revenue: ForecastPoint[];
  roas: ForecastPoint[];
  summary: {
    expectedRevenue: number;
    lowerRevenue: number;
    upperRevenue: number;
    avgRoas: number;
    horizonDays: number;
    level: "overall" | "channel" | "campaign_type" | "campaign";
    value?: string;
    modelType: string;
    diagnostics?: {
      revenueFitMapePct: number;
      roasFitMapePct: number;
      revenueIntervalCoveragePct: number;
      roasIntervalCoveragePct: number;
      trainingDays: number;
      topRevenueFeatures: Array<{ feature: string; importance: number }>;
      topRoasFeatures: Array<{ feature: string; importance: number }>;
    };
  };
  validation: ValidationResult;
}

export interface SimChannelResult {
  channel: string;
  horizonDays: number;
  baselineDailySpend: number;
  newDailySpend: number;
  baselineTotalSpend: number;
  newTotalSpend: number;
  baselineRevenue: number;
  projectedRevenue: number;
  projectedRevenueLower: number;
  projectedRevenueUpper: number;
  baselineRoas: number;
  projectedRoas: number;
  daily: ForecastPoint[];
}

export interface SimulationApiResponse {
  channels: SimChannelResult[];
  totals: {
    totalNewSpend: number;
    totalBaseSpend: number;
    totalProjectedRevenue: number;
    totalProjectedRevenueLower: number;
    totalProjectedRevenueUpper: number;
    totalBaselineRevenue: number;
    projectedRoas: number;
    baselineRoas: number;
    revenueChangePct: number;
    roasChangePct: number;
  };
  validation: ValidationResult;
}

export interface InsightsResponse {
  executiveSummary: string;
  revenueDrivers: Array<{ title: string; detail: string; metric?: string }>;
  channelPerformance: Array<{
    channel: string;
    verdict: "outperforming" | "on_track" | "underperforming";
    insight: string;
    recommendation: string;
  }>;
  campaignPerformance: {
    top: Array<{ name: string; channel: string; insight: string }>;
    bottom: Array<{ name: string; channel: string; issue: string; action: string }>;
  };
  budgetAllocation: Array<{
    channel: string;
    currentSharePct: number;
    recommendedSharePct: number;
    rationale: string;
    expectedImpact: string;
  }>;
  risks: Array<{
    title: string;
    severity: "low" | "medium" | "high";
    description: string;
    mitigation: string;
  }>;
  growthOpportunities: Array<{
    title: string;
    description: string;
    expectedImpact: string;
    effort: "low" | "medium" | "high";
  }>;
  actionPlan: Array<{
    priority: "high" | "medium" | "low";
    timeline: string;
    owner: string;
    action: string;
    kpi: string;
  }>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Backend request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function validateRowsApi(rows: CampaignRow[]) {
  return postJson<ValidationResult>("/api/validate", { rows });
}

export function fetchForecastApi(
  rows: CampaignRow[],
  horizon: 30 | 60 | 90,
  level: "overall" | "channel" | "campaign_type" | "campaign",
  value?: string,
) {
  return postJson<ForecastApiResponse>("/api/forecast", { rows, horizon, level, value });
}

export function simulateBudgetsApi(
  rows: CampaignRow[],
  horizon: 30 | 60 | 90,
  budgets: Record<string, number>,
) {
  return postJson<SimulationApiResponse>("/api/simulate", { rows, horizon, budgets });
}

export function generateInsightsApi(summary: Record<string, unknown>) {
  return postJson<InsightsResponse>("/api/insights", { summary });
}
