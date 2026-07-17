import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type React from "react";
import { DataProvider } from "@/lib/data-store";
import { generateDemoData } from "@/lib/demo-data";
import type {
  DecisionSupportResponse,
  ForecastApiResponse,
  InsightsResponse,
  SimulationApiResponse,
  SpendCurveResponse,
} from "@/lib/backend-api";
import { UploadPage } from "./app.upload";
import { ForecastPage } from "./app.forecast";
import { SimulatorPage } from "./app.simulator";
import { InsightsPage } from "./app.insights";

const apiMocks = vi.hoisted(() => ({
  validateRowsApi: vi.fn(),
  fetchForecastApi: vi.fn(),
  simulateBudgetsApi: vi.fn(),
  decisionSupportApi: vi.fn(),
  fetchSpendCurveApi: vi.fn(),
  fetchAnomaliesApi: vi.fn(),
  generateInsightsApi: vi.fn(),
  fetchModelValidationApi: vi.fn(),
}));

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}));

vi.mock("@/lib/backend-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/backend-api")>();
  return {
    ...actual,
    validateRowsApi: apiMocks.validateRowsApi,
    fetchForecastApi: apiMocks.fetchForecastApi,
    simulateBudgetsApi: apiMocks.simulateBudgetsApi,
    decisionSupportApi: apiMocks.decisionSupportApi,
    fetchSpendCurveApi: apiMocks.fetchSpendCurveApi,
    fetchAnomaliesApi: apiMocks.fetchAnomaliesApi,
    generateInsightsApi: apiMocks.generateInsightsApi,
    fetchModelValidationApi: apiMocks.fetchModelValidationApi,
  };
});

vi.mock("@/lib/ai-insights", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai-insights")>();
  return { ...actual, generateInsightsApi: apiMocks.generateInsightsApi };
});

vi.mock("sonner", () => ({ toast: toastMocks }));

function renderWithData(ui: React.ReactElement) {
  localStorage.clear();
  return render(<DataProvider>{ui}</DataProvider>);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function forecastResponse(horizonDays: 30 | 60 | 90): ForecastApiResponse {
  return {
    revenue: [
      { date: "2026-01-01", value: 1000, lower: 900, upper: 1100, historical: true },
      { date: "2026-01-02", value: 1200, lower: 1000, upper: 1400, historical: false },
    ],
    roas: [
      { date: "2026-01-01", value: 3, lower: 2.8, upper: 3.2, historical: true },
      { date: "2026-01-02", value: 3.2, lower: 2.9, upper: 3.5, historical: false },
    ],
    summary: {
      expectedRevenue: 1200,
      lowerRevenue: 1000,
      upperRevenue: 1400,
      avgRoas: 3.2,
      lowerRoas: 2.9,
      upperRoas: 3.5,
      roasStatus: "computable",
      horizonDays,
      level: "overall",
      modelType: "xgboost",
    },
    validation: { rows: [], issues: [], totalRows: 1, validRows: 1 },
  };
}

function simulationResponse(): SimulationApiResponse {
  return {
    channels: ["Google Ads", "Meta Ads", "Microsoft Ads"].map((channel, index) => ({
      channel,
      horizonDays: 30,
      baselineDailySpend: 100 + index * 10,
      newDailySpend: 110 + index * 10,
      baselineTotalSpend: 3000,
      newTotalSpend: 3300,
      baselineRevenue: 9000,
      projectedRevenue: 9900,
      projectedRevenueLower: 9000,
      projectedRevenueUpper: 10800,
      baselineRoas: 3,
      projectedRoas: 3,
      daily: [],
    })),
    totals: {
      totalNewSpend: 9900,
      totalBaseSpend: 9000,
      totalProjectedRevenue: 29700,
      totalProjectedRevenueLower: 27000,
      totalProjectedRevenueUpper: 32400,
      totalBaselineRevenue: 27000,
      projectedRoas: 3,
      baselineRoas: 3,
      revenueChangePct: 10,
      roasChangePct: 0,
    },
    validation: { rows: [], issues: [], totalRows: 1, validRows: 1 },
  };
}

function decisionResponse(): DecisionSupportResponse {
  return {
    optimizer: {
      currentBudget: 9000,
      recommendedBudget: 9500,
      expectedRevenue: 31000,
      expectedRoas: 3.2,
      expectedProfit: 21500,
      targetGapRevenue: 0,
      targetGapRoas: 0,
      baselineExpectedRevenue: 29700,
      optimizedExpectedRevenue: 31000,
      absoluteGain: 1300,
      gainPct: 4.38,
      baselineIntervalHalfWidth: 2700,
      optimizedIntervalHalfWidth: 2800,
      uncertaintyNoiseFloor: 5500,
      uncertaintyCalculation:
        "Noise floor = baseline half-width $2,700.00 + optimized half-width $2,800.00 = $5,500.00; projected gain = $1,300.00.",
      meaningful: false,
      outcome: "IMPROVED_WITHIN_NOISE",
      verdict: "Hypothesis, not guarantee: the projected gain is inside forecast uncertainty.",
      safeBudgetCeilings: { "Google Ads": 4000, "Meta Ads": 4000, "Microsoft Ads": 4000 },
      maxSupportedTotalBudget: 12000,
      constraintNotes: ["Allocations are reconciled to cents."],
      recommendations: [
        {
          channel: "Google Ads",
          currentBudget: 3000,
          recommendedBudget: 3500,
          deltaBudget: 500,
          currentSharePct: 33,
          recommendedSharePct: 37,
          expectedRevenue: 12000,
          expectedRoas: 3.4,
          rationale: "Shift budget toward higher intent demand.",
        },
      ],
    },
    scenarios: [
      {
        name: "Base (0%)",
        totalSpend: 9000,
        projectedRevenue: 27000,
        projectedRoas: 3,
        projectedProfit: 18000,
        revenueDeltaPct: 0,
        roasDeltaPct: 0,
        profitDelta: 0,
        budgets: { "Google Ads": 3000 },
      },
    ],
    risks: [],
    opportunities: [],
    channelHealth: [
      {
        channel: "Google Ads",
        score: 91,
        status: "healthy",
        revenueTrendPct: 5,
        roasTrendPct: 2,
        spendSharePct: 33,
        revenueSharePct: 45,
        drivers: ["Strong ROAS"],
      },
    ],
    planningZones: ["Google Ads", "Meta Ads", "Microsoft Ads"].map((channel) => ({
      channel,
      plannedBudget: 3000,
      recentBaselineBudget: 3000,
      historicalP90: 4000,
      historicalMaximum: 4200,
      safeBudgetCeiling: 4000,
      ratioVsP90: 0.75,
      overshootPct: 0,
      comparableWindowCount: 12,
      zone: "SUPPORTED" as const,
      confidenceImpact: "none" as const,
      underinvestmentRisk: false,
      reason: "Planned spend is within the historical p90 of comparable windows.",
    })),
    overallPlanZone: {
      zone: "SUPPORTED",
      weightedSeverityScore: 0,
      unsupportedChannels: [],
      plannedBudget: 9000,
      maxSupportedTotalBudget: 12000,
      reason: "Spend-weighted severity is 0.00 on a 0-3 scale.",
    },
    validation: { rows: [], issues: [], totalRows: 1, validRows: 1 },
  };
}

function spendCurveResponse(): SpendCurveResponse {
  return {
    curve: [
      { spend: 1000, revenue: 3000, roas: 3 },
      { spend: 3000, revenue: 9000, roas: 3 },
    ],
    saturation_spend: 5000,
    marginal_roas: 2.4,
  };
}

function modelValidationResponse() {
  return {
    generatedAt: "2026-07-04T00:00:00Z",
    source: "reports/backtest_report.json",
    modelType: "trained_model",
    consistency: { badge_pct: 15 },
    rows: [
      {
        horizonDays: 30,
        folds: 3,
        segments: 54,
        trainedRevenueMae: 2180.83,
        trainedRevenueRmse: 3212.65,
        trainedRevenueMape: 2.23,
        trainedRevenueCoverage: 100,
        trainedRevenueWidthPct: 66.5,
        trainedRoasMae: 0.05,
        trainedRoasRmse: 0.06,
        trainedRoasCoverage: 100,
        baselineRevenueMae: 3097.88,
        baselineRevenueRmse: 4501.73,
        baselineRevenueMape: 3.15,
        revenueWinner: "trained_model",
      },
    ],
  };
}

function insightsResponse(): InsightsResponse {
  return {
    executiveSummary: "Revenue is improving because high-intent demand is expanding.",
    revenueDrivers: [{ title: "Google Ads demand", detail: "Search revenue is accelerating." }],
    channelPerformance: [
      {
        channel: "Google Ads",
        verdict: "outperforming",
        insight: "ROAS is above blended average.",
        recommendation: "Increase budget carefully.",
      },
    ],
    campaignPerformance: {
      top: [{ name: "Brand Search", channel: "Google Ads", insight: "Efficient demand capture." }],
      bottom: [
        {
          name: "Prospecting",
          channel: "Meta Ads",
          issue: "Lower short-term ROAS.",
          action: "Refresh creative.",
        },
      ],
    },
    budgetAllocation: [
      {
        channel: "Google Ads",
        currentSharePct: 40,
        recommendedSharePct: 45,
        rationale: "Highest marginal return.",
        expectedImpact: "Revenue lift",
      },
    ],
    risks: [
      {
        title: "Meta softness",
        severity: "medium",
        description: "Prospecting efficiency may decline.",
        mitigation: "Limit increases until ROAS recovers.",
      },
    ],
    growthOpportunities: [
      {
        title: "Search expansion",
        description: "Scale high-intent keywords.",
        expectedImpact: "Incremental revenue",
        effort: "low",
      },
    ],
    actionPlan: [
      {
        priority: "high",
        timeline: "Next 7 days",
        owner: "Marketing manager",
        action: "Move budget to Google Ads",
        kpi: "ROAS",
      },
    ],
  };
}

describe("core dashboard route behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.validateRowsApi.mockResolvedValue({
      rows: generateDemoData(1).slice(0, 1),
      issues: [],
      totalRows: 1,
      validRows: 1,
    });
    apiMocks.fetchForecastApi.mockResolvedValue(forecastResponse(30));
    apiMocks.simulateBudgetsApi.mockResolvedValue(simulationResponse());
    apiMocks.decisionSupportApi.mockResolvedValue(decisionResponse());
    apiMocks.fetchSpendCurveApi.mockResolvedValue(spendCurveResponse());
    apiMocks.fetchModelValidationApi.mockResolvedValue(modelValidationResponse());
    apiMocks.fetchAnomaliesApi.mockResolvedValue({
      anomalies: [],
      trendBreaks: [],
      driverEvidence: [],
      causalEstimates: [],
    });
    apiMocks.generateInsightsApi.mockResolvedValue(insightsResponse());
  });

  it("shows per-row CSV validation details after upload", async () => {
    apiMocks.validateRowsApi.mockResolvedValueOnce({
      rows: generateDemoData(1).slice(0, 1),
      issues: [{ row: 2, type: "invalid_revenue", message: "Negative revenue" }],
      totalRows: 1,
      validRows: 1,
    });
    const user = userEvent.setup();
    const { container } = renderWithData(<UploadPage />);
    const csv = [
      "date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue",
      "2026-01-01,Google Ads,Search,Brand Search,100,10,1000,2,400",
    ].join("\n");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).toBeTruthy();

    await user.upload(input!, new File([csv], "campaigns.csv", { type: "text/csv" }));

    expect(await screen.findByText("Validation details")).toBeInTheDocument();
    const table = screen.getAllByRole("table")[0];
    expect(within(table).getByText("Row")).toBeInTheDocument();
    expect(within(table).getByText("invalid revenue")).toBeInTheDocument();
    expect(within(table).getByText("Negative revenue")).toBeInTheDocument();
  });

  it("lets the user change the forecast horizon selector", async () => {
    const user = userEvent.setup();
    renderWithData(<ForecastPage />);
    expect(await screen.findByText("Revenue forecast")).toBeInTheDocument();

    await user.click(screen.getAllByRole("combobox")[0]);
    await user.click(await screen.findByRole("option", { name: "60 days" }));

    await waitFor(() => {
      expect(apiMocks.fetchForecastApi).toHaveBeenLastCalledWith(
        expect.any(Array),
        60,
        "overall",
        undefined,
      );
    });
  });

  it("renders backend forecast revenue and ROAS values", async () => {
    renderWithData(<ForecastPage />);

    expect(await screen.findByText("Revenue forecast")).toBeInTheDocument();
    expect(await screen.findByText("Model Validation")).toBeInTheDocument();
    expect(screen.getByTestId("model-path-confidence")).toBeInTheDocument();
    expect(await screen.findByText("$1,200")).toBeInTheDocument();
    expect(await screen.findByText("3.20x")).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchForecastApi).toHaveBeenCalled());
  });

  it("loads simulator scenarios and exposes budget scenario buttons", async () => {
    renderWithData(<SimulatorPage />);

    expect(await screen.findByText("What-If Scenarios")).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.decisionSupportApi).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Base (0%)" })).toHaveClass("border-primary");
    expect(screen.getByRole("button", { name: "+50%" })).toBeInTheDocument();
    expect(await screen.findByText("Projected revenue")).toBeInTheDocument();
    expect(screen.getByTestId("automatic-allocation")).toBeInTheDocument();
    expect(screen.getAllByText(/Hypothesis, not guarantee/i)).not.toHaveLength(0);
  });

  it("switches budget modes while preserving total and sends exact automatic allocations", async () => {
    const user = userEvent.setup();
    renderWithData(<SimulatorPage />);

    const totalInput = await screen.findByLabelText("Total budget");
    await user.clear(totalInput);
    await user.type(totalInput, "10001");

    await waitFor(() => {
      const latestCall = apiMocks.simulateBudgetsApi.mock.calls.at(-1);
      const payload = latestCall?.[2] as Record<string, number>;
      expect(Object.values(payload).reduce((sum, value) => sum + value, 0)).toBe(10001);
    });

    await user.click(screen.getByRole("button", { name: "Manual channel budgets" }));
    expect(screen.queryByTestId("automatic-allocation")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Google Ads planned budget input")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Automatic allocation" }));
    expect(await screen.findByDisplayValue("10001")).toBeInTheDocument();
  });

  it("covers AI insights ready, loading, and error states", async () => {
    const pending = deferred<InsightsResponse>();
    apiMocks.generateInsightsApi.mockReturnValueOnce(pending.promise);
    const user = userEvent.setup();
    renderWithData(<InsightsPage />);

    expect(await screen.findByText("Ready when you are")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /generate insights/i }));
    expect(await screen.findByText(/Analyzing .* rows across/i)).toBeInTheDocument();
    pending.resolve(insightsResponse());
    expect(
      await screen.findByText("Revenue is improving because high-intent demand is expanding."),
    ).toBeInTheDocument();

    apiMocks.generateInsightsApi.mockRejectedValueOnce(new Error("Gemini unavailable"));
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    await waitFor(() => expect(toastMocks.error).toHaveBeenCalledWith("Gemini unavailable"));
  });
});
