export type FrontierScenario = {
  name: string;
  totalSpend: number;
  projectedRevenue: number;
  projectedRoas: number;
  projectedProfit: number;
  revenueDeltaPct: number;
  roasDeltaPct: number;
  profitDelta: number;
};

export type FrontierPoint = FrontierScenario & {
  riskLevel: "low" | "medium" | "high";
  uncertaintyWidthPct: number;
  isHighestRevenue: boolean;
  isHighestRoas: boolean;
  isLowestRisk: boolean;
  isRecommended: boolean;
  isDiminishingReturn: boolean;
  recommendationLabel: string;
  score: number;
};

function normalize(value: number, min: number, max: number) {
  if (!Number.isFinite(value) || max <= min) return 0.5;
  return Math.max(0, Math.min(1, (value - min) / (max - min)));
}

function riskScore(scenario: FrontierScenario) {
  let score = 0;
  if (scenario.roasDeltaPct < -8) score += 3;
  else if (scenario.roasDeltaPct < -4) score += 2;
  else if (scenario.roasDeltaPct < 0) score += 1;
  if (scenario.revenueDeltaPct < -2) score += 1;
  if (scenario.profitDelta < 0) score += 1;
  if (scenario.totalSpend > 0 && scenario.projectedRevenue / scenario.totalSpend < 1) score += 1;
  return Math.min(4, score);
}

function riskLabel(score: number): FrontierPoint["riskLevel"] {
  if (score >= 3) return "high";
  if (score >= 1) return "medium";
  return "low";
}

export function buildEfficientFrontier(scenarios: FrontierScenario[]): FrontierPoint[] {
  if (!scenarios.length) return [];
  const spends = scenarios.map((scenario) => scenario.totalSpend);
  const revenues = scenarios.map((scenario) => scenario.projectedRevenue);
  const roas = scenarios.map((scenario) => scenario.projectedRoas);
  const maxRevenue = Math.max(...revenues);
  const maxRoas = Math.max(...roas);
  const minRisk = Math.min(...scenarios.map(riskScore));
  const sorted = [...scenarios].sort((a, b) => a.totalSpend - b.totalSpend);
  const marginalByName = new Map<string, number>();
  for (let index = 1; index < sorted.length; index += 1) {
    const previous = sorted[index - 1];
    const current = sorted[index];
    const spendDelta = current.totalSpend - previous.totalSpend;
    const revenueDelta = current.projectedRevenue - previous.projectedRevenue;
    marginalByName.set(current.name, spendDelta > 0 ? revenueDelta / spendDelta : 0);
  }
  const marginalValues = [...marginalByName.values()].filter(Number.isFinite);
  const medianMarginal =
    marginalValues.length > 0
      ? [...marginalValues].sort((a, b) => a - b)[Math.floor(marginalValues.length / 2)]
      : 0;
  const minSpend = Math.min(...spends);
  const maxSpend = Math.max(...spends);
  const minRevenue = Math.min(...revenues);
  const maxRevenueRange = Math.max(...revenues);
  const minRoas = Math.min(...roas);
  const maxRoasRange = Math.max(...roas);

  const scored = scenarios.map((scenario) => {
    const risk = riskScore(scenario);
    const score =
      normalize(scenario.projectedRevenue, minRevenue, maxRevenueRange) * 0.42 +
      normalize(scenario.projectedRoas, minRoas, maxRoasRange) * 0.38 +
      normalize(
        scenario.projectedProfit,
        Math.min(...scenarios.map((item) => item.projectedProfit)),
        Math.max(...scenarios.map((item) => item.projectedProfit)),
      ) *
        0.2 -
      risk * 0.11;
    const uncertaintyWidthPct = Math.max(
      8,
      Math.min(
        65,
        Math.abs(scenario.revenueDeltaPct) * 0.55 + Math.max(0, -scenario.roasDeltaPct) * 0.9 + 10,
      ),
    );
    return {
      ...scenario,
      riskLevel: riskLabel(risk),
      uncertaintyWidthPct,
      isHighestRevenue: scenario.projectedRevenue === maxRevenue,
      isHighestRoas: scenario.projectedRoas === maxRoas,
      isLowestRisk: risk === minRisk,
      isRecommended: false,
      isDiminishingReturn:
        scenario.totalSpend > minSpend &&
        scenario.totalSpend < maxSpend + 1 &&
        (marginalByName.get(scenario.name) ?? Number.POSITIVE_INFINITY) < medianMarginal,
      recommendationLabel: "",
      score,
    } satisfies FrontierPoint;
  });

  const recommendedIndex = scored.reduce((bestIndex, point, index) => {
    if (point.score > scored[bestIndex].score) return index;
    return bestIndex;
  }, 0);

  return scored.map((point, index) => ({
    ...point,
    isRecommended: index === recommendedIndex,
    recommendationLabel:
      index === recommendedIndex
        ? "Recommended balanced option"
        : point.isHighestRevenue
          ? "Highest revenue"
          : point.isHighestRoas
            ? "Highest ROAS"
            : point.isLowestRisk
              ? "Lowest risk"
              : point.isDiminishingReturn
                ? "Diminishing-return watch"
                : "Scenario option",
  }));
}
