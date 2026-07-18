import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  ForecastConfidencePanel,
  ForecastContributionWaterfall,
  ForecastEvidencePanel,
  HistoricalForecastComparison,
  WhyThisModelPanel,
} from "./forecast-evidence";

describe("forecast evidence presentation", () => {
  it("renders generated metrics, artifact provenance and horizon model reasons", () => {
    render(
      <>
        <ForecastEvidencePanel />
        <WhyThisModelPanel />
      </>,
    );

    expect(screen.getByTestId("forecast-evidence-panel")).toHaveTextContent("2.81%");
    expect(screen.getByTestId("forecast-evidence-panel")).toHaveTextContent(
      "Deterministic · offline capable",
    );
    expect(screen.getByTestId("forecast-evidence-panel")).toHaveTextContent(
      "2025-08-22 to 2026-05-18",
    );
    expect(screen.getByTestId("why-this-model")).toHaveTextContent("Safe baseline challenger");
    expect(screen.getAllByText("Major limitation")).toHaveLength(3);
  });

  it("shows numeric comparisons, partial-source recovery and confidence factors", () => {
    render(
      <>
        <HistoricalForecastComparison
          horizon={30}
          historicalRevenue={1000}
          expectedRevenue={1200}
          lowerRevenue={900}
          upperRevenue={1400}
          historicalRoas={3}
          expectedRoas={3.2}
          channels={[]}
          partialError="One channel failed."
        />
        <ForecastConfidencePanel
          inputs={{
            readiness: null,
            historyDays: 20,
            freshnessDays: 18,
            missingValueRatePct: 12,
            modelPath: "trained_model",
            intervalWidthPct: 42,
            sampleCount: 40,
            budgetZone: "HIGH_EXTRAPOLATION",
          }}
        />
      </>,
    );

    expect(screen.getByTestId("historical-forecast-comparison")).toHaveTextContent("+20.0%");
    expect(screen.getByText(/retry the forecast or select an individual channel/i)).toBeVisible();
    expect(screen.getByText(/available channels remain displayed/i)).toBeVisible();
    expect(screen.getByTestId("forecast-confidence-explanation")).toHaveTextContent(
      "Confidence reductions",
    );
    expect(screen.getByText(/wide at 42.0%/i)).toBeVisible();
  });

  it("uses only supplied local effects in the contribution waterfall", () => {
    render(
      <ForecastContributionWaterfall
        drivers={[
          {
            feature: "spend",
            label: "Media spend",
            direction: "positive",
            impact: 0.42,
            explanation: "Above the historical median.",
          },
          {
            feature: "lag_revenue",
            label: "Recent revenue",
            direction: "negative",
            impact: -0.21,
            explanation: "Below the historical median.",
          },
        ]}
      />,
    );

    const waterfall = screen.getByTestId("forecast-contribution-waterfall");
    expect(waterfall).toHaveTextContent("+0.420");
    expect(waterfall).toHaveTextContent("−0.210");
    expect(waterfall).toHaveTextContent("not an additive revenue reconciliation");
  });
});
