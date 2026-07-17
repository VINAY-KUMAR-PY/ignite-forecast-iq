import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InsightsResponse } from "./backend-api";

const pdfMocks = vi.hoisted(() => ({ constructor: vi.fn() }));

vi.mock("jspdf", () => ({ default: pdfMocks.constructor }));

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
    pdfMocks.constructor.mockReset();
    pdfMocks.constructor.mockImplementation(() => {
      throw new Error("PDF unavailable in unit test");
    });
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
    await expect(capturedBlob?.text()).resolves.toContain("Planning ranges are not guarantees");
  });

  it("generates the PDF path when jsPDF is available", () => {
    let pageCount = 1;
    const save = vi.fn();
    pdfMocks.constructor.mockImplementation(function MockPdf() {
      return {
        setFontSize: vi.fn(),
        setTextColor: vi.fn(),
        text: vi.fn(),
        splitTextToSize: vi.fn((value: string) => [value]),
        addPage: vi.fn(() => {
          pageCount += 1;
        }),
        getNumberOfPages: vi.fn(() => pageCount),
        setPage: vi.fn(),
        save,
      };
    });

    exportExecutivePdfReport(
      {
        totalRevenue: 10000,
        totalSpend: 2500,
        avgRoas: 4,
        forecast30dRevenue: 12000,
        forecast30dRevenueLower: 10000,
        forecast30dRevenueUpper: 14000,
        revenueTrendPct: 5,
        roasTrendPct: -1,
        channels: [],
      },
      {
        executiveSummary: "Revenue remains stable.",
        revenueDrivers: [],
        channelPerformance: [],
        campaignPerformance: { top: [], bottom: [] },
        budgetAllocation: [],
        risks: [],
        growthOpportunities: [],
        actionPlan: [],
      },
    );

    expect(save).toHaveBeenCalledWith(expect.stringMatching(/^ForecastIQ_Executive_Brief_/));
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
