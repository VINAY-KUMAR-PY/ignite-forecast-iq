import { expect, test } from "@playwright/test";

test("CSV upload covers dashboard, forecasts, simulator, and fallback insights", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto("/app/upload");
  await page.locator('input[type="file"]').setInputFiles("data/sample_campaigns.csv");
  await expect(page.getByText("Uploaded dataset")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Validation details")).toBeVisible();
  await expect(page.getByText("All rows passed validation.")).toBeVisible();

  await page.getByRole("link", { name: /decision center/i }).click();
  await expect(page.getByTestId("business-impact-dashboard")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("executive-decision-center")).toBeVisible();

  await page.getByRole("link", { name: /forecasting/i }).click();
  await expect(page.getByRole("heading", { name: "Revenue forecast" })).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByRole("heading", { name: "ROAS forecast" })).toBeVisible();
  await expect(page.getByTestId("confidence-intervals")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("Expected revenue (30d)")).toBeVisible();

  await page.getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: "60 days" }).click();
  await expect(page.getByText("Expected revenue (60d)")).toBeVisible({ timeout: 45_000 });

  await page.getByRole("combobox").nth(0).click();
  await page.getByRole("option", { name: "90 days" }).click();
  await expect(page.getByText("Expected revenue (90d)")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId("explainability-center")).toBeVisible();
  await expect(page.getByTestId("model-validation-panel")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Model Validation" })).toBeVisible();
  await expect(page.getByText("30 days")).toBeVisible();

  await page.getByRole("link", { name: /budget simulator/i }).click();
  await expect(page.getByRole("heading", { name: "What-If Scenarios" })).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByTestId("model-path-confidence")).toBeVisible();
  await expect(page.getByRole("button", { name: "Base (0%)" })).toBeVisible();
  await page.getByRole("button", { name: "+20%" }).click();
  await expect(page.getByText("Spend efficiency analysis")).toBeVisible();
  await page.getByRole("button", { name: "Base (0%)" }).click();
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
          "Deterministic fallback insights generated because Gemini is unavailable for this workflow test.",
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
  await expect(page.getByText(/Fallback mode is intentional/i)).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("button", { name: /generate insights/i })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: /generate insights/i }).click();
  await expect(page.getByText(/Executive summary/i)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/Deterministic fallback insights generated/i)).toBeVisible();
  await expect(page.getByText(/Action plan/i)).toBeVisible();

  const actionableErrors = consoleErrors.filter(
    (entry) => !entry.includes("favicon") && !entry.includes("ResizeObserver"),
  );
  expect(actionableErrors).toEqual([]);
});
