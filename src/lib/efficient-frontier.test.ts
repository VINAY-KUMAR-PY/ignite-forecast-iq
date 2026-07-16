import { describe, expect, it } from "vitest";
import { buildEfficientFrontier, type FrontierScenario } from "./efficient-frontier";

const scenarios: FrontierScenario[] = [
  {
    name: "Conservative",
    totalSpend: 80_000,
    projectedRevenue: 310_000,
    projectedRoas: 3.88,
    projectedProfit: 230_000,
    revenueDeltaPct: -4,
    roasDeltaPct: 2,
    profitDelta: -5_000,
  },
  {
    name: "Base",
    totalSpend: 100_000,
    projectedRevenue: 400_000,
    projectedRoas: 4,
    projectedProfit: 300_000,
    revenueDeltaPct: 0,
    roasDeltaPct: 0,
    profitDelta: 0,
  },
  {
    name: "Aggressive",
    totalSpend: 140_000,
    projectedRevenue: 500_000,
    projectedRoas: 3.57,
    projectedProfit: 360_000,
    revenueDeltaPct: 25,
    roasDeltaPct: -10,
    profitDelta: 60_000,
  },
];

describe("buildEfficientFrontier", () => {
  it("maps scenarios to spend/revenue frontier points with deterministic recommendations", () => {
    const frontier = buildEfficientFrontier(scenarios);

    expect(frontier).toHaveLength(3);
    expect(frontier.filter((point) => point.isRecommended)).toHaveLength(1);
    expect(frontier.some((point) => point.isHighestRevenue)).toBe(true);
    expect(frontier.some((point) => point.isHighestRoas)).toBe(true);
    expect(frontier.some((point) => point.isLowestRisk)).toBe(true);
  });

  it("flags higher-risk diminishing return options without using LLM output", () => {
    const frontier = buildEfficientFrontier(scenarios);
    const aggressive = frontier.find((point) => point.name === "Aggressive");

    expect(aggressive?.riskLevel).toBe("high");
    expect(aggressive?.uncertaintyWidthPct).toBeGreaterThan(10);
    expect(aggressive?.recommendationLabel).toMatch(
      /Highest revenue|Diminishing-return|Scenario|Recommended/,
    );
  });

  it("handles empty scenario arrays for loading and empty states", () => {
    expect(buildEfficientFrontier([])).toEqual([]);
  });
});
