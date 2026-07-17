import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { DataReadinessScoreCard } from "./data-readiness-score";
import type { DataReadinessRating, DataReadinessScore } from "@/lib/types";

function readinessScore(score = 82, rating: DataReadinessRating = "Good"): DataReadinessScore {
  return {
    score,
    rating,
    evaluatedAsOf: "2026-07-17",
    confidenceExplanation:
      "The data is suitable for forecasting, but listed gaps may widen uncertainty.",
    components: [
      {
        key: "schema_required",
        label: "Schema and required fields",
        score: 95,
        weight: 20,
        summary: "All core fields mapped with high adapter confidence.",
      },
      {
        key: "completeness_validity",
        label: "Completeness and validity",
        score: 80,
        weight: 20,
        summary: "A small number of values need review.",
      },
      {
        key: "historical_coverage",
        label: "Historical coverage",
        score: 70,
        weight: 20,
        summary: "120 days of history are available.",
      },
      {
        key: "freshness",
        label: "Data freshness",
        score: 90,
        weight: 10,
        summary: "The latest observation is current.",
      },
      {
        key: "channel_campaign_coverage",
        label: "Channel and campaign coverage",
        score: 75,
        weight: 10,
        summary: "Two usable channels are available.",
      },
      {
        key: "spend_revenue_consistency",
        label: "Spend and revenue consistency",
        score: 85,
        weight: 10,
        summary: "Spend and revenue coverage is strong.",
      },
      {
        key: "outliers_duplicates",
        label: "Outliers and duplicates",
        score: 75,
        weight: 10,
        summary: "One duplicate row needs review.",
      },
    ],
    positiveEvidence: ["Core fields were recognized.", "Fresh observations are available."],
    warnings: ["Only 120 days of usable history are available."],
    recommendedActions: ["Provide at least 180 days of history."],
    metrics: {
      historyDays: 120,
      validRows: 420,
      usableChannels: 2,
      dateConsistencyPct: 100,
    },
  };
}

afterEach(() => {
  document.documentElement.classList.remove("dark");
});

describe("Data Readiness Score UI", () => {
  it("renders the numeric score, rating, component breakdown, warnings, and recommendations", () => {
    render(<DataReadinessScoreCard score={readinessScore()} status="available" context="upload" />);

    expect(screen.getByTestId("data-readiness-value")).toHaveTextContent("82");
    expect(screen.getByTestId("data-readiness-rating")).toHaveTextContent("Good");
    const breakdown = screen.getByTestId("data-readiness-components");
    expect(within(breakdown).getByText("Schema and required fields")).toBeInTheDocument();
    expect(within(breakdown).getByText("95/100")).toBeInTheDocument();
    expect(screen.getByText("Only 120 days of usable history are available.")).toBeInTheDocument();
    expect(screen.getByText("Provide at least 180 days of history.")).toBeInTheDocument();
    expect(screen.getByLabelText("82 out of 100, Good")).toBeInTheDocument();
  });

  it.each([
    [95, "Excellent"],
    [82, "Good"],
    [68, "Usable with caution"],
    [42, "Needs attention"],
  ] as const)("renders the %s score rating as %s", (score, rating) => {
    render(
      <DataReadinessScoreCard
        score={readinessScore(score, rating)}
        status="available"
        context="decision"
      />,
    );

    expect(screen.getByTestId("data-readiness-rating")).toHaveTextContent(rating);
  });

  it("expands the keyboard-accessible scoring methodology", async () => {
    const user = userEvent.setup();
    render(<DataReadinessScoreCard score={readinessScore()} status="available" context="upload" />);

    const summary = screen.getByText("How this score is calculated");
    summary.focus();
    expect(summary.tagName).toBe("SUMMARY");
    expect(summary).toHaveFocus();
    await user.click(summary);

    expect(summary.closest("details")).toHaveAttribute("open");
    expect(screen.getByText(/overall score is the rounded weighted sum/i)).toBeVisible();
  });

  it("remains visible in light and dark themes", () => {
    const { rerender } = render(
      <DataReadinessScoreCard score={readinessScore()} status="available" context="forecast" />,
    );
    expect(screen.getByTestId("data-readiness-score")).toBeVisible();
    expect(screen.getByText("Data quality and forecast confidence")).toBeVisible();

    document.documentElement.classList.add("dark");
    rerender(
      <DataReadinessScoreCard score={readinessScore()} status="available" context="forecast" />,
    );
    expect(screen.getByTestId("data-readiness-score")).toBeVisible();
    expect(document.documentElement).toHaveClass("dark");
  });

  it("uses a single-column mobile-first layout without hiding evidence", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    render(<DataReadinessScoreCard score={readinessScore()} status="available" context="upload" />);

    expect(screen.getByTestId("data-readiness-components")).toHaveClass("grid-cols-1");
    expect(screen.getByText("Warnings")).toBeVisible();
    expect(screen.getByText("Recommended actions")).toBeVisible();
  });

  it("shows an honest fallback when backend scoring is missing", async () => {
    const user = userEvent.setup();
    let retried = false;
    render(
      <DataReadinessScoreCard
        score={null}
        status="unavailable"
        error="API offline"
        context="upload"
        onRetry={() => {
          retried = true;
        }}
      />,
    );

    expect(screen.getByTestId("data-readiness-fallback")).toHaveTextContent(
      "Data Readiness Score unavailable",
    );
    expect(screen.getByText(/will not invent a score/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry score" }));
    expect(retried).toBe(true);
  });
});
