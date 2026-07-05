import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InsightsResponse } from "./backend-api";

vi.mock("jspdf", () => ({
  default: vi.fn(() => {
    throw new Error("PDF unavailable in unit test");
  }),
}));

vi.mock("jspdf-autotable", () => ({ default: vi.fn() }));

const { exportExecutivePdfReport } = await import("./report-export");

describe("report export business logic", () => {
  let capturedBlob: Blob | undefined;
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    capturedBlob = undefined;
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn((blob: Blob) => {
        capturedBlob = blob;
        return "blob:forecastiq-report";
      }),
      revokeObjectURL: vi.fn(),
    });
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  it("falls back to a text executive report when PDF generation is unavailable", async () => {
    const insights: InsightsResponse = {
      executiveSummary: "Revenue is stable and budget changes should be tested gradually.",
      revenueDrivers: [],
      channelPerformance: [],
      campaignPerformance: { top: [], bottom: [] },
      budgetAllocation: [],
      risks: [],
      growthOpportunities: [],
      actionPlan: [],
    };

    exportExecutivePdfReport(
      {
        totalRevenue: 10000,
        totalSpend: 2500,
        avgRoas: 4,
        forecast30dRevenue: 12000,
        forecast60dRevenue: 24000,
        forecast90dRevenue: 36000,
        revenueTrendPct: 5,
        roasTrendPct: -1,
        channels: [],
      },
      insights,
    );

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:forecastiq-report");
    await expect(capturedBlob?.text()).resolves.toContain("ForecastIQ Executive Briefing");
    await expect(capturedBlob?.text()).resolves.toContain(
      "Review budget scenarios and monitor forecast interval width",
    );
  });
});
