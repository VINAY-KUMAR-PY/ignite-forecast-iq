import { expect, test } from "@playwright/test";

test("Try Live Demo covers Forecast, Simulator, and Insights", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto("/");
  await page
    .getByRole("link", { name: /try live demo/i })
    .first()
    .click();
  await expect(page).toHaveURL(/\/app/);
  await expect(page.getByTestId("business-impact-dashboard")).toBeVisible({ timeout: 30_000 });

  await page.getByRole("link", { name: /forecasting/i }).click();
  await expect(page.getByRole("heading", { name: "Revenue forecast" })).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByRole("heading", { name: "ROAS forecast" })).toBeVisible();
  await expect(page.getByTestId("confidence-intervals")).toBeVisible({ timeout: 45_000 });

  await page.getByRole("link", { name: /budget simulator/i }).click();
  await expect(page.getByRole("heading", { name: "What-If Scenarios" })).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByRole("button", { name: "Base (0%)" })).toBeVisible();
  await expect(page.getByText("Projected revenue").first()).toBeVisible();

  await page.route("**/api/anomalies", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        anomalies: [],
        trendBreaks: [],
        driverEvidence: [],
        causalEstimates: [],
      }),
    });
  });
  await page.route("**/api/insights", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        executiveSummary:
          "ForecastIQ expects revenue growth from high-intent channels while keeping fallback AI insights deterministic for demos.",
        revenueDrivers: [
          {
            title: "High-intent search demand",
            detail: "Google Ads is carrying efficient revenue with stable ROAS.",
            metric: "+12% revenue lift",
          },
        ],
        channelPerformance: [
          {
            channel: "Google Ads",
            verdict: "outperforming",
            insight: "Search campaigns are above the blended ROAS benchmark.",
            recommendation: "Increase budget gradually and monitor marginal ROAS.",
          },
        ],
        campaignPerformance: {
          top: [
            {
              name: "Brand Search",
              channel: "Google Ads",
              insight: "Efficient capture of existing demand.",
            },
          ],
          bottom: [
            {
              name: "Prospecting",
              channel: "Meta Ads",
              issue: "Lower short-term efficiency.",
              action: "Refresh creative before scaling.",
            },
          ],
        },
        budgetAllocation: [
          {
            channel: "Google Ads",
            currentSharePct: 40,
            recommendedSharePct: 45,
            rationale: "Highest marginal return in the current mix.",
            expectedImpact: "Incremental revenue without lowering blended ROAS.",
          },
        ],
        risks: [
          {
            title: "Prospecting fatigue",
            severity: "medium",
            description: "Upper-funnel campaigns may soften if creative is not refreshed.",
            mitigation: "Cap spend increases until new creative is validated.",
          },
        ],
        growthOpportunities: [
          {
            title: "Scale efficient search",
            description: "Expand high-intent keyword coverage before broad prospecting.",
            expectedImpact: "Near-term revenue lift",
            effort: "low",
          },
        ],
        actionPlan: [
          {
            priority: "high",
            timeline: "Next 7 days",
            owner: "Marketing manager",
            action: "Move incremental budget into Google Ads while tracking ROAS daily.",
            kpi: "Revenue and ROAS",
          },
        ],
        causalHypotheses: [
          {
            rank: 1,
            title: "Budget shift drove incremental revenue",
            confidence: "medium",
            hypothesis: "Observed revenue gains are consistent with higher search investment.",
            supportingEvidence: ["Demo causal evidence supports a search-side lift."],
            contradictingEvidence: ["Requires continued validation with holdout tests."],
            recommendedTest: "Run a geo or campaign-level holdout.",
          },
        ],
      }),
    });
  });

  await page.getByRole("link", { name: /ai insights/i }).click();
  await expect(page.getByRole("button", { name: /generate insights/i })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: /generate insights/i }).click();
  await expect(page.getByText(/Executive summary/i)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/Action plan/i)).toBeVisible();

  const actionableErrors = consoleErrors.filter(
    (entry) => !entry.includes("favicon") && !entry.includes("ResizeObserver"),
  );
  expect(actionableErrors).toEqual([]);
});
