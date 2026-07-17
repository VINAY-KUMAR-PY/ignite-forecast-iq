import type { CampaignRow, ForecastPoint, ValidationResult } from "./types";

const DEFAULT_API_BASE = import.meta.env.PROD
  ? "https://forecastiq-api.onrender.com"
  : "http://127.0.0.1:8000";
const API_BASE = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE).replace(/\/$/, "");

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
      explainabilityMethod?: string;
      shap_method?: "shap" | "feature_importances_fallback";
      shap_importance?: Array<{
        feature: string;
        shap_value: number;
        direction: "positive" | "negative";
      }>;
      whyThisForecast?: Array<{
        feature: string;
        label: string;
        direction: "positive" | "negative";
        impact: number;
        explanation: string;
      }>;
      whyThisForecastSummary?: string;
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
  baselineExpectedRevenue: number;
  optimizedExpectedRevenue: number;
  absoluteGain: number;
  gainPct: number;
  baselineIntervalHalfWidth: number;
  optimizedIntervalHalfWidth: number;
  uncertaintyNoiseFloor: number;
  uncertaintyCalculation: string;
  meaningful: boolean;
  outcome:
    | "NO_CHANGE"
    | "INFEASIBLE"
    | "IMPROVED_WITHIN_NOISE"
    | "IMPROVED_ABOVE_NOISE"
    | "DEGRADED";
  verdict: string;
  safeBudgetCeilings: Record<string, number>;
  maxSupportedTotalBudget: number;
  constraintNotes: string[];
  recommendations: BudgetRecommendation[];
}

export type PlanningZone = "SUPPORTED" | "CAUTION" | "HIGH_EXTRAPOLATION" | "UNSUPPORTED";

export interface ChannelPlanningZone {
  channel: string;
  plannedBudget: number;
  recentBaselineBudget: number;
  historicalP90: number;
  historicalMaximum: number;
  safeBudgetCeiling: number;
  ratioVsP90?: number | null;
  overshootPct?: number | null;
  comparableWindowCount: number;
  zone: PlanningZone;
  confidenceImpact: "none" | "moderate" | "material" | "severe";
  underinvestmentRisk: boolean;
  reason: string;
}

export interface OverallPlanningZone {
  zone: PlanningZone;
  weightedSeverityScore: number;
  unsupportedChannels: string[];
  plannedBudget: number;
  maxSupportedTotalBudget: number;
  reason: string;
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

export interface WhatIfScenarioInput {
  name: string;
  budgetMultipliers: Record<string, number>;
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
  planningZones: ChannelPlanningZone[];
  overallPlanZone: OverallPlanningZone;
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
  causalHypotheses?: Array<{
    rank: number;
    title: string;
    confidence: "low" | "medium" | "high";
    hypothesis: string;
    supportingEvidence: string[];
    contradictingEvidence: string[];
    recommendedTest: string;
  }>;
  provenance?: {
    mode: "deterministic_offline" | "live_gemini";
    networkUsedForResult: boolean;
    networkRequired: boolean;
    evidenceSource: string[];
    generatedAt: string;
    limitations: string[];
  };
}

export interface SpendCurveResponse {
  curve: Array<{ spend: number; revenue: number; roas: number }>;
  saturation_spend: number;
  marginal_roas: number;
}

export interface ModelValidationRow {
  horizonDays: 30 | 60 | 90;
  folds: number;
  segments: number;
  trainedRevenueMae: number;
  trainedRevenueRmse: number;
  trainedRevenueMape: number;
  trainedRevenueCoverage: number;
  trainedRevenueWidthPct: number;
  trainedRoasMae: number;
  trainedRoasRmse: number;
  trainedRoasCoverage: number;
  baselineRevenueMae: number;
  baselineRevenueRmse: number;
  baselineRevenueMape: number;
  revenueWinner: string;
}

export interface ModelValidationResponse {
  generatedAt: string;
  source: string;
  modelType: string;
  consistency: {
    badge_pct?: number;
    max_revenue_delta_pct?: number;
    max_roas_delta_pct?: number;
    interpretation?: string;
  };
  rows: ModelValidationRow[];
}

interface SpendCurveRequest {
  rows: CampaignRow[];
  channel: string;
  horizon: 30 | 60 | 90;
  currentBudget: number;
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
  causalEstimates: Array<{
    date: string;
    channel: string;
    metric: string;
    method: string;
    preWindowDays: number;
    postWindowDays: number;
    incrementalRevenue: number;
    lowerRevenue: number;
    upperRevenue: number;
    roasEffect: number;
    confidence: "low" | "medium" | "high";
    interpretation: string;
  }>;
}

interface AnomalyRequest {
  rows: CampaignRow[];
}

function finiteNonNegative(value: unknown, fallback = 0): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 ? numeric : fallback;
}

function requiredText(value: unknown, fallback: string): string {
  const text = typeof value === "string" ? value.trim() : "";
  return text || fallback;
}

function safeRows(rows: CampaignRow[]): CampaignRow[] {
  const cleaned = rows
    .map((row) => {
      const date = requiredText(row.date, "");
      const channel = requiredText(row.channel, "");
      const campaignType = requiredText(row.campaign_type, "Unclassified");
      const campaignName = requiredText(row.campaign_name, campaignType);
      if (!date || !channel) return null;
      const spend = finiteNonNegative(row.spend);
      const revenue = finiteNonNegative(row.revenue);
      const roas = Number.isFinite(Number(row.roas))
        ? finiteNonNegative(row.roas)
        : spend > 0
          ? revenue / spend
          : 0;
      return {
        date,
        channel,
        campaign_type: campaignType,
        campaign_name: campaignName,
        spend,
        clicks: finiteNonNegative(row.clicks),
        impressions: finiteNonNegative(row.impressions),
        conversions: finiteNonNegative(row.conversions),
        revenue,
        roas,
      };
    })
    .filter((row): row is CampaignRow => row !== null);

  if (!cleaned.length) {
    throw new Error("No valid campaign rows are available for the backend request.");
  }
  return cleaned;
}

function observedChannels(rows: CampaignRow[]): string[] {
  return [...new Set(rows.map((row) => row.channel).filter(Boolean))];
}

function safeBudgetMap(
  rows: CampaignRow[],
  budgets: Record<string, number>,
): Record<string, number> {
  const channels = observedChannels(rows);
  if (!channels.length) {
    throw new Error("At least one campaign channel is required for budget simulation.");
  }
  return Object.fromEntries(
    channels.map((channel) => [channel, finiteNonNegative(budgets[channel])]),
  );
}

function safeTargets(
  targets: { targetRevenue?: number; targetRoas?: number },
  budgets: Record<string, number>,
) {
  const totalBudget = Object.values(budgets).reduce(
    (sum, value) => sum + finiteNonNegative(value),
    0,
  );
  if (totalBudget <= 0) {
    return { targetRevenue: 0, targetRoas: 0 };
  }
  return {
    targetRevenue: finiteNonNegative(targets.targetRevenue),
    targetRoas: finiteNonNegative(targets.targetRoas),
  };
}

function safeScenarios(
  rows: CampaignRow[],
  scenarios: WhatIfScenarioInput[],
): WhatIfScenarioInput[] {
  const channels = observedChannels(rows);
  return scenarios.map((scenario) => ({
    name: requiredText(scenario.name, "Scenario"),
    budgetMultipliers: Object.fromEntries(
      channels.map((channel) => [
        channel,
        finiteNonNegative(scenario.budgetMultipliers?.[channel], 1),
      ]),
    ),
  }));
}

function safeSpendCurveChannel(rows: CampaignRow[], channel: string): string {
  const channels = observedChannels(rows);
  return channels.includes(channel) ? channel : channels[0];
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "network request failed";
    throw new Error(`Failed to reach ForecastIQ backend at ${API_BASE}${path}: ${message}`);
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Backend request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "network request failed";
    throw new Error(`Failed to reach ForecastIQ backend at ${API_BASE}${path}: ${message}`);
  }
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
  const cleanedRows = safeRows(rows);
  const body = { rows: cleanedRows, horizon, budgets: safeBudgetMap(cleanedRows, budgets) };
  return postJson<SimulationApiResponse>("/api/simulate", body);
}

export function decisionSupportApi(
  rows: CampaignRow[],
  horizon: 30 | 60 | 90,
  budgets: Record<string, number>,
  targets: { targetRevenue?: number; targetRoas?: number } = {},
  scenarios: WhatIfScenarioInput[] = [],
) {
  const cleanedRows = safeRows(rows);
  const cleanedBudgets = safeBudgetMap(cleanedRows, budgets);
  const body = {
    rows: cleanedRows,
    horizon,
    budgets: cleanedBudgets,
    ...safeTargets(targets, cleanedBudgets),
    scenarios: safeScenarios(cleanedRows, scenarios),
  };
  return postJson<DecisionSupportResponse>("/api/decision-support", body);
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
  const cleanedRows = safeRows(rows);
  const body: SpendCurveRequest = {
    rows: cleanedRows,
    channel: safeSpendCurveChannel(cleanedRows, channel),
    horizon,
    currentBudget: finiteNonNegative(currentBudget),
  };
  return postJson<SpendCurveResponse>("/api/spend-curve", body);
}

export function fetchAnomaliesApi(rows: CampaignRow[]) {
  const body: AnomalyRequest = { rows };
  return postJson<AnomalyResponse>("/api/anomalies", body);
}

export function fetchModelValidationApi() {
  return getJson<ModelValidationResponse>("/api/model-validation");
}
