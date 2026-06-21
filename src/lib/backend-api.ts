import type { CampaignRow, ForecastPoint, ValidationResult } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export interface ForecastApiResponse {
  revenue: ForecastPoint[];
  roas: ForecastPoint[];
  summary: {
    expectedRevenue: number;
    lowerRevenue: number;
    upperRevenue: number;
    avgRoas: number;
    lowerRoas: number;
    upperRoas: number;
    roasStatus: "computable" | "not_computable" | string;
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
      topRevenueFeatures: Array<{ feature: string; importance: number; label?: string | null }>;
      topRoasFeatures: Array<{ feature: string; importance: number; label?: string | null }>;
      revenueAccuracy: AccuracyMetrics;
      roasAccuracy: AccuracyMetrics;
      revenueExplanation: string;
      roasExplanation: string;
      businessBrief: {
        summary: string;
        risks: string[];
        opportunities: string[];
        recommendedActions: string[];
      };
    };
  };
  validation: ValidationResult;
}

export interface AccuracyMetrics {
  mae: number;
  rmse: number;
  mapePct: number;
  r2Score: number;
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
  roas_decomposition?: Array<{
    channel: string;
    spend: number;
    revenue: number;
    roas: number;
    roas_vs_blend: number;
    marginal_roas_estimate: number;
    efficiency_score: number;
  }>;
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

export interface BudgetRecommendation {
  channel: string;
  currentBudget: number;
  recommendedBudget: number;
  deltaBudget: number;
  currentSharePct: number;
  recommendedSharePct: number;
  expectedRevenue: number;
  expectedRoas: number;
  rationale: string;
}

export interface BudgetOptimizerResult {
  targetRevenue?: number | null;
  targetRoas?: number | null;
  currentBudget: number;
  recommendedBudget: number;
  expectedRevenue: number;
  expectedRoas: number;
  expectedProfit: number;
  targetGapRevenue: number;
  targetGapRoas: number;
  recommendations: BudgetRecommendation[];
}

export interface WhatIfScenarioResult {
  name: string;
  totalSpend: number;
  projectedRevenue: number;
  projectedRoas: number;
  projectedProfit: number;
  revenueDeltaPct: number;
  roasDeltaPct: number;
  profitDelta: number;
  budgets: Record<string, number>;
}

export interface DetectionItem {
  type: string;
  channel?: string | null;
  severity: "low" | "medium" | "high";
  score: number;
  message: string;
  recommendation: string;
}

export interface ChannelHealthScore {
  channel: string;
  score: number;
  status: "healthy" | "watch" | "critical";
  revenueTrendPct: number;
  roasTrendPct: number;
  spendSharePct: number;
  revenueSharePct: number;
  drivers: string[];
}

export interface DecisionSupportResponse {
  optimizer: BudgetOptimizerResult;
  scenarios: WhatIfScenarioResult[];
  risks: DetectionItem[];
  opportunities: DetectionItem[];
  channelHealth: ChannelHealthScore[];
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

export interface SpendCurveResponse {
  curve: Array<{ spend: number; revenue: number; roas: number }>;
  saturation_spend: number;
  marginal_roas: number;
}

export interface AnomalyItem {
  date: string;
  channel: string;
  metric: string;
  actual: number;
  expected: number;
  z_score: number;
  severity: "warning" | "critical";
  description: string;
}

export interface AnomalyResponse {
  anomalies: AnomalyItem[];
  trendBreaks: Array<{
    date: string;
    channel: string;
    direction: "up" | "down";
    magnitude_pct: number;
  }>;
  driverEvidence: Array<{
    channel: string;
    observations: number;
    spendRevenueDeltaCorrelation: number;
    channelRevenueDeltaCorrelation: number | null;
    laggedRevenueDeltaCorrelation: number | null;
    direction: "positive" | "negative" | "mixed";
    strength: "weak" | "moderate" | "strong";
    interpretation: string;
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

export function decisionSupportApi(
  rows: CampaignRow[],
  horizon: 30 | 60 | 90,
  budgets: Record<string, number>,
  targets: { targetRevenue?: number; targetRoas?: number } = {},
) {
  return postJson<DecisionSupportResponse>("/api/decision-support", {
    rows,
    horizon,
    budgets,
    targetRevenue: targets.targetRevenue,
    targetRoas: targets.targetRoas,
  });
}

export function generateInsightsApi(summary: Record<string, unknown>) {
  return postJson<InsightsResponse>("/api/insights", { summary });
}

export function fetchSpendCurveApi(
  rows: CampaignRow[],
  channel: string,
  horizon: 30 | 60 | 90,
  currentBudget: number,
) {
  return postJson<SpendCurveResponse>("/api/spend-curve", {
    rows,
    channel,
    horizon,
    current_budget: currentBudget,
  });
}

export function fetchAnomaliesApi(rows: CampaignRow[]) {
  return postJson<AnomalyResponse>("/api/anomalies", { rows });
}
