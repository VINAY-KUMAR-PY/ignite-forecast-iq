import { describe, expect, it } from "vitest";
import { buildEvidenceBundle } from "./evidence-bundle";
import type { ForecastSnapshot } from "./data-store";
import type { InsightsResponse } from "./backend-api";

const insights: InsightsResponse = {
  executiveSummary: "Evidence-based summary.",
  revenueDrivers: [],
  channelPerformance: [],
  campaignPerformance: { top: [], bottom: [] },
  budgetAllocation: [],
  risks: [],
  growthOpportunities: [],
  actionPlan: [],
  causalHypotheses: [
    {
      rank: 1,
      title: "Search lift",
      confidence: "medium",
      hypothesis: "Search may have contributed.",
      supportingEvidence: ["Observed lift"],
      contradictingEvidence: ["No holdout"],
      recommendedTest: "Run a holdout.",
    },
  ],
  provenance: {
    mode: "deterministic_offline",
    networkUsedForResult: false,
    networkRequired: false,
    evidenceSource: ["Uploaded rows"],
    generatedAt: "2026-07-17T00:00:00Z",
    limitations: ["Observational evidence only."],
  },
};

const forecast: ForecastSnapshot = {
  horizon: 30,
  level: "overall",
  response: {
    revenue: [{ date: "2026-07-18", value: 1200, lower: 1000, upper: 1400 }],
    roas: [{ date: "2026-07-18", value: 3.2, lower: 2.9, upper: 3.5 }],
    summary: {
      expectedRevenue: 1200,
      lowerRevenue: 1000,
      upperRevenue: 1400,
      avgRoas: 3.2,
      lowerRoas: 2.9,
      upperRoas: 3.5,
      roasStatus: "computable",
      horizonDays: 30,
      level: "overall",
      modelType: "trained_model",
    },
    validation: { rows: [], issues: [], totalRows: 1, validRows: 1 },
  },
};

describe("ForecastIQ Evidence Bundle", () => {
  it("contains forecast CSV, model, causal, limitations and provenance evidence", () => {
    const bundle = buildEvidenceBundle({
      executiveReport: { totalRevenue: 1000 },
      insights,
      forecast,
      planning: null,
      dataReadiness: null,
    });

    expect(bundle.contents.predictionsCsv).toContain("expected_revenue");
    expect(bundle.contents.predictionsCsv).toContain("2026-07-18,1200,1000,1400");
    expect(bundle.contents.modelEvidence.availability).toBe("available");
    expect(bundle.contents.causalEvidence).toHaveLength(1);
    expect(bundle.contents.limitations).toContain("Observational evidence only.");
    expect(bundle.contents.provenanceConfiguration.deterministicOfflineVerified).toBe(true);
    expect(bundle.contents.scenarioComparison).toMatchObject({ status: "unavailable" });
  });

  it("uses actionable fallbacks when forecast and planning snapshots are missing", () => {
    const bundle = buildEvidenceBundle({
      executiveReport: {},
      insights,
      forecast: null,
      planning: null,
      dataReadiness: null,
    });

    expect(bundle.contents.predictionsCsv).toContain("Run the Forecasting page");
    expect(bundle.contents.scenarioComparison).toMatchObject({
      nextStep: expect.stringContaining("Budget Simulator"),
    });
    expect(bundle.contents.dataReadinessReport).toMatchObject({
      nextStep: expect.stringContaining("Data Upload"),
    });
  });
});
