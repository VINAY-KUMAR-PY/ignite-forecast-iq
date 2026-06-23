"""Pydantic contracts shared by the API, frontend and CLI workflows."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


ForecastLevel = Literal["overall", "channel", "campaign_type", "campaign"]
Horizon = Literal[30, 60, 90]


class CampaignRow(BaseModel):
    date: str
    channel: str
    campaign_type: str
    campaign_name: str
    spend: float = Field(ge=0)
    clicks: float = Field(ge=0)
    impressions: float = Field(ge=0)
    conversions: float = Field(ge=0)
    revenue: float = Field(ge=0)
    roas: Optional[float] = None

    @field_validator("channel", "campaign_type", "campaign_name")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class ValidationIssue(BaseModel):
    type: str
    row: int
    message: str


class ValidationResponse(BaseModel):
    rows: List[CampaignRow]
    issues: List[ValidationIssue]
    totalRows: int
    validRows: int


class ValidationRequest(BaseModel):
    rows: List[Dict[str, Any]]


class ForecastPoint(BaseModel):
    date: str
    value: float
    lower: float
    upper: float
    historical: bool = False


class FeatureImportance(BaseModel):
    feature: str
    importance: float
    label: Optional[str] = None


class ForecastContribution(BaseModel):
    feature: str
    label: str
    direction: Literal["positive", "negative"]
    impact: float
    explanation: str


class AccuracyMetrics(BaseModel):
    mae: float
    rmse: float
    mapePct: float
    r2Score: float


class ForecastBusinessBrief(BaseModel):
    summary: str
    risks: List[str]
    opportunities: List[str]
    recommendedActions: List[str]


class ForecastDiagnostics(BaseModel):
    revenueFitMapePct: float
    roasFitMapePct: float
    revenueIntervalCoveragePct: float
    roasIntervalCoveragePct: float
    trainingDays: int
    topRevenueFeatures: List[FeatureImportance]
    topRoasFeatures: List[FeatureImportance]
    revenueAccuracy: AccuracyMetrics
    roasAccuracy: AccuracyMetrics
    revenueExplanation: str
    roasExplanation: str
    explainabilityMethod: str = "permutation_baseline"
    shap_importance: List[Dict[str, Any]] = Field(default_factory=list)
    whyThisForecast: List[ForecastContribution] = Field(default_factory=list)
    whyThisForecastSummary: str = ""
    businessBrief: ForecastBusinessBrief


class ForecastRequest(BaseModel):
    rows: List[CampaignRow]
    horizon: Horizon = 30
    level: ForecastLevel = "overall"
    value: Optional[str] = None


class ForecastSummary(BaseModel):
    expectedRevenue: float
    lowerRevenue: float
    upperRevenue: float
    avgRoas: float
    lowerRoas: float = 0.0
    upperRoas: float = 0.0
    roasStatus: str = "computable"
    horizonDays: int
    level: ForecastLevel
    value: Optional[str] = None
    modelType: str
    diagnostics: Optional[ForecastDiagnostics] = None


class ForecastResponse(BaseModel):
    revenue: List[ForecastPoint]
    roas: List[ForecastPoint]
    summary: ForecastSummary
    validation: ValidationResponse


class SimulationRequest(BaseModel):
    rows: List[CampaignRow]
    horizon: Horizon = 30
    budgets: Dict[str, float] = Field(default_factory=dict)


class SimChannelResult(BaseModel):
    channel: str
    horizonDays: int
    baselineDailySpend: float
    newDailySpend: float
    baselineTotalSpend: float
    newTotalSpend: float
    baselineRevenue: float
    projectedRevenue: float
    projectedRevenueLower: float
    projectedRevenueUpper: float
    baselineRoas: float
    projectedRoas: float
    daily: List[ForecastPoint]


class SimulationTotals(BaseModel):
    totalNewSpend: float
    totalBaseSpend: float
    totalProjectedRevenue: float
    totalProjectedRevenueLower: float
    totalProjectedRevenueUpper: float
    totalBaselineRevenue: float
    projectedRoas: float
    baselineRoas: float
    revenueChangePct: float
    roasChangePct: float


class RoasDecompositionItem(BaseModel):
    channel: str
    spend: float
    revenue: float
    roas: float
    roas_vs_blend: float
    marginal_roas_estimate: float
    efficiency_score: int


class SimulationResponse(BaseModel):
    channels: List[SimChannelResult]
    totals: SimulationTotals
    validation: ValidationResponse
    roas_decomposition: List[RoasDecompositionItem] = Field(default_factory=list)


class WhatIfScenarioInput(BaseModel):
    name: str
    budgetMultipliers: Dict[str, float] = Field(default_factory=dict)


class DecisionSupportRequest(BaseModel):
    rows: List[CampaignRow]
    horizon: Horizon = 30
    budgets: Dict[str, float] = Field(default_factory=dict)
    targetRevenue: Optional[float] = Field(default=None, ge=0)
    targetRoas: Optional[float] = Field(default=None, ge=0)
    scenarios: List[WhatIfScenarioInput] = Field(default_factory=list)


class BudgetRecommendation(BaseModel):
    channel: str
    currentBudget: float
    recommendedBudget: float
    deltaBudget: float
    currentSharePct: float
    recommendedSharePct: float
    expectedRevenue: float
    expectedRoas: float
    rationale: str


class BudgetOptimizerResult(BaseModel):
    targetRevenue: Optional[float] = None
    targetRoas: Optional[float] = None
    currentBudget: float
    recommendedBudget: float
    expectedRevenue: float
    expectedRoas: float
    expectedProfit: float
    targetGapRevenue: float
    targetGapRoas: float
    recommendations: List[BudgetRecommendation]


class WhatIfScenarioResult(BaseModel):
    name: str
    totalSpend: float
    projectedRevenue: float
    projectedRoas: float
    projectedProfit: float
    revenueDeltaPct: float
    roasDeltaPct: float
    profitDelta: float
    budgets: Dict[str, float]


class DetectionItem(BaseModel):
    type: str
    channel: Optional[str] = None
    severity: Literal["low", "medium", "high"]
    score: float
    message: str
    recommendation: str


class ChannelHealthScore(BaseModel):
    channel: str
    score: float
    status: Literal["healthy", "watch", "critical"]
    revenueTrendPct: float
    roasTrendPct: float
    spendSharePct: float
    revenueSharePct: float
    drivers: List[str]


class DecisionSupportResponse(BaseModel):
    optimizer: BudgetOptimizerResult
    scenarios: List[WhatIfScenarioResult]
    risks: List[DetectionItem]
    opportunities: List[DetectionItem]
    channelHealth: List[ChannelHealthScore]
    validation: ValidationResponse


class InsightsRequest(BaseModel):
    summary: Dict[str, Any]


class RevenueDriver(BaseModel):
    title: str
    detail: str
    metric: Optional[str] = None


class ChannelPerformance(BaseModel):
    channel: str
    verdict: Literal["outperforming", "on_track", "underperforming"]
    insight: str
    recommendation: str


class CampaignTop(BaseModel):
    name: str
    channel: str
    insight: str


class CampaignBottom(BaseModel):
    name: str
    channel: str
    issue: str
    action: str


class CampaignPerformance(BaseModel):
    top: List[CampaignTop]
    bottom: List[CampaignBottom]


class BudgetAllocation(BaseModel):
    channel: str
    currentSharePct: float
    recommendedSharePct: float
    rationale: str
    expectedImpact: str


class Risk(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    description: str
    mitigation: str


class GrowthOpportunity(BaseModel):
    title: str
    description: str
    expectedImpact: str
    effort: Literal["low", "medium", "high"]


class ActionPlanItem(BaseModel):
    priority: Literal["high", "medium", "low"]
    timeline: str
    owner: str
    action: str
    kpi: str


class InsightsResponse(BaseModel):
    executiveSummary: str
    revenueDrivers: List[RevenueDriver]
    channelPerformance: List[ChannelPerformance]
    campaignPerformance: CampaignPerformance
    budgetAllocation: List[BudgetAllocation]
    risks: List[Risk]
    growthOpportunities: List[GrowthOpportunity]
    actionPlan: List[ActionPlanItem]


class TrainRequest(BaseModel):
    rows: List[CampaignRow]
    modelPath: str = "pickle/model.pkl"


class TrainResponse(BaseModel):
    modelPath: str
    modelType: str
    trainingRows: int
    message: str
