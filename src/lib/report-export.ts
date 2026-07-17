import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import type { DecisionSupportResponse, InsightsResponse } from "@/lib/backend-api";

export type ExecutiveReportSummary = {
  totalRevenue: number;
  totalSpend: number;
  avgRoas: number;
  forecast30dRevenue: number;
  forecast60dRevenue?: number;
  forecast90dRevenue?: number;
  forecast30dRevenueLower?: number;
  forecast30dRevenueUpper?: number;
  revenueTrendPct: number;
  roasTrendPct: number;
  channels: Array<{
    name: string;
    revenue: number;
    spend: number;
    roas: number;
    forecast30dRevenue: number;
    forecast30dRoas: number;
  }>;
};

export interface ExecutiveReportContext {
  dataPeriod?: string;
  selectedHorizon?: 30 | 60 | 90;
  selectedForecastMethod?: string;
  allocationMode?: "automatic" | "manual";
  plannedBudgets?: Record<string, number>;
  decisionSupport?: DecisionSupportResponse;
}

const currency = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);

const roas = (value: number) => `${value.toFixed(2)}x`;
const today = () => new Date().toISOString().slice(0, 10);
const timestamp = () => new Date().toISOString();

export function exportExecutivePdfReport(
  summary: ExecutiveReportSummary,
  insights: InsightsResponse,
  context: ExecutiveReportContext = {},
): void {
  try {
    const doc = new jsPDF();
    addFooter(doc);

    doc.setFontSize(24);
    doc.text("ForecastIQ Executive Briefing", 18, 34);
    doc.setFontSize(11);
    doc.text(`Date: ${today()}`, 18, 48);
    doc.text("Client: Demo ecommerce account", 18, 56);
    doc.text("Prepared for: NetElixir AIgnition 3.0", 18, 64);
    doc.text(`Data period: ${context.dataPeriod ?? "Not supplied"}`, 18, 72);
    doc.setFontSize(13);
    doc.text("Executive Summary", 18, 86);
    doc.setFontSize(10);
    doc.text(doc.splitTextToSize(insights.executiveSummary, 170), 18, 96);

    doc.addPage();
    addFooter(doc);
    doc.setFontSize(16);
    doc.text("KPI Summary", 18, 24);
    autoTable(doc, {
      startY: 34,
      head: [["Metric", "Value"]],
      body: [
        ["Revenue", currency(summary.totalRevenue)],
        ["Spend", currency(summary.totalSpend)],
        ["ROAS", roas(summary.avgRoas)],
        ["Forecast 30d", currency(summary.forecast30dRevenue)],
        ["Forecast 60d", currency(summary.forecast60dRevenue ?? 0)],
        ["Forecast 90d", currency(summary.forecast90dRevenue ?? 0)],
        [
          "30d planning range",
          `${currency(summary.forecast30dRevenueLower ?? 0)} to ${currency(summary.forecast30dRevenueUpper ?? 0)}`,
        ],
        ["Selected method", context.selectedForecastMethod ?? "Deterministic local summary"],
      ],
    });

    doc.addPage();
    addFooter(doc);
    doc.setFontSize(16);
    doc.text("Channel Breakdown", 18, 24);
    autoTable(doc, {
      startY: 34,
      head: [["Channel", "Revenue", "Spend", "ROAS", "30d Forecast", "30d ROAS"]],
      body: summary.channels.map((channel) => [
        channel.name,
        currency(channel.revenue),
        currency(channel.spend),
        roas(channel.roas),
        currency(channel.forecast30dRevenue),
        roas(channel.forecast30dRoas),
      ]),
    });

    doc.addPage();
    addFooter(doc);
    doc.setFontSize(16);
    doc.text("Budget Recommendations", 18, 24);
    writeBullets(
      doc,
      insights.budgetAllocation
        .slice(0, 3)
        .map(
          (item) =>
            `${item.channel}: move from ${item.currentSharePct.toFixed(1)}% to ${item.recommendedSharePct.toFixed(1)}%. ${item.expectedImpact}. ${item.rationale}`,
        ),
      36,
    );

    if (context.decisionSupport) {
      const optimizer = context.decisionSupport.optimizer;
      doc.addPage();
      addFooter(doc);
      doc.setFontSize(16);
      doc.text("Budget Planning Evidence", 18, 24);
      autoTable(doc, {
        startY: 34,
        head: [["Channel", "Planned", "Zone", "Safe ceiling"]],
        body: context.decisionSupport.planningZones.map((zone) => [
          zone.channel,
          currency(context.plannedBudgets?.[zone.channel] ?? zone.plannedBudget),
          zone.zone.replaceAll("_", " "),
          currency(zone.safeBudgetCeiling),
        ]),
      });
      doc.setFontSize(11);
      doc.text(
        doc.splitTextToSize(
          `Overall support: ${context.decisionSupport.overallPlanZone.zone.replaceAll("_", " ")}. ` +
            `Allocation mode: ${context.allocationMode ?? "not supplied"}. ` +
            `Optimizer outcome: ${optimizer.outcome.replaceAll("_", " ")}. ` +
            `Gain ${currency(optimizer.absoluteGain)} versus noise floor ${currency(optimizer.uncertaintyNoiseFloor)}. ` +
            `${optimizer.verdict}`,
          170,
        ),
        18,
        115,
      );
      doc.setFontSize(10);
      doc.text(
        doc.splitTextToSize(`Calculation: ${optimizer.uncertaintyCalculation}`, 170),
        18,
        145,
      );
    }

    doc.addPage();
    addFooter(doc);
    doc.setFontSize(16);
    doc.text("Risk & Opportunity Summary", 18, 24);
    doc.setFontSize(12);
    doc.text("Risks", 18, 38);
    writeBullets(
      doc,
      insights.risks
        .slice(0, 4)
        .map((item) => `${item.title}: ${item.description} Mitigation: ${item.mitigation}`),
      48,
    );
    doc.setFontSize(12);
    doc.text("Opportunities", 18, 118);
    writeBullets(
      doc,
      insights.growthOpportunities
        .slice(0, 4)
        .map((item) => `${item.title}: ${item.description} Upside: ${item.expectedImpact}`),
      128,
    );
    doc.setFontSize(10);
    doc.text(
      doc.splitTextToSize(
        `AI mode: ${insights.provenance?.mode ?? "metadata unavailable"}; network required: no. ` +
          "Causal limitation: observational attribution and DiD evidence support testable hypotheses, not randomized incrementality proof. " +
          "Lower/P10-style, expected/P50-style and upper/P90-style values are planning cases, not guarantees.",
        170,
      ),
      18,
      205,
    );

    doc.save(`ForecastIQ_Executive_Brief_${today()}.pdf`);
  } catch {
    downloadTextReport(summary, insights, context);
  }
}

function downloadTextReport(
  summary: ExecutiveReportSummary,
  insights: InsightsResponse,
  context: ExecutiveReportContext,
) {
  const optimizer = context.decisionSupport?.optimizer;
  const primaryRecommendation =
    insights.actionPlan?.[0]?.action ??
    insights.budgetAllocation?.[0]?.rationale ??
    "Review budget scenarios and monitor forecast interval width before changing spend.";
  const lines = [
    "ForecastIQ Executive Briefing",
    `Generated: ${timestamp()}`,
    `Data period: ${context.dataPeriod ?? "Not supplied"}`,
    `Selected horizon: ${context.selectedHorizon ?? 30} days`,
    `Selected forecast method: ${context.selectedForecastMethod ?? "Deterministic local summary"}`,
    "",
    "Executive Summary",
    insights.executiveSummary,
    "",
    "Forecast Summary",
    `30-day revenue forecast: ${currency(summary.forecast30dRevenue)}`,
    `60-day revenue forecast: ${currency(summary.forecast60dRevenue ?? 0)}`,
    `90-day revenue forecast: ${currency(summary.forecast90dRevenue ?? 0)}`,
    `Average ROAS: ${roas(summary.avgRoas)}`,
    `Lower / P10-style downside planning case: ${currency(summary.forecast30dRevenueLower ?? 0)}`,
    `Expected / P50-style central planning case: ${currency(summary.forecast30dRevenue)}`,
    `Upper / P90-style upside planning case: ${currency(summary.forecast30dRevenueUpper ?? 0)}`,
    "Planning ranges are not guarantees.",
    `Revenue trend: ${summary.revenueTrendPct.toFixed(1)}%`,
    `ROAS trend: ${summary.roasTrendPct.toFixed(1)}%`,
    "",
    "Key Recommendation",
    primaryRecommendation,
    "",
    "KPI Summary",
    `Revenue: ${currency(summary.totalRevenue)}`,
    `Spend: ${currency(summary.totalSpend)}`,
    `ROAS: ${roas(summary.avgRoas)}`,
    `Forecast 30d: ${currency(summary.forecast30dRevenue)}`,
    `Forecast 60d: ${currency(summary.forecast60dRevenue ?? 0)}`,
    `Forecast 90d: ${currency(summary.forecast90dRevenue ?? 0)}`,
    "",
    "Budget Recommendations",
    ...insights.budgetAllocation
      .slice(0, 3)
      .map(
        (item) =>
          `- ${item.channel}: move from ${item.currentSharePct.toFixed(1)}% to ${item.recommendedSharePct.toFixed(1)}%. ${item.expectedImpact}. ${item.rationale}`,
      ),
    ...(context.decisionSupport
      ? [
          "",
          "Budget Planning Evidence",
          `Allocation mode: ${context.allocationMode ?? "Not supplied"}`,
          `Total planned budget: ${currency(Object.values(context.plannedBudgets ?? {}).reduce((sum, value) => sum + value, 0))}`,
          ...context.decisionSupport.planningZones.map(
            (zone) =>
              `- ${zone.channel}: ${currency(context.plannedBudgets?.[zone.channel] ?? zone.plannedBudget)}, ${zone.zone.replaceAll("_", " ")}, safe ceiling ${currency(zone.safeBudgetCeiling)}.`,
          ),
          `Overall plan support: ${context.decisionSupport.overallPlanZone.zone.replaceAll("_", " ")}`,
          `Optimizer outcome: ${optimizer?.outcome.replaceAll("_", " ")}`,
          `Expected gain: ${currency(optimizer?.absoluteGain ?? 0)}`,
          `Uncertainty noise floor: ${currency(optimizer?.uncertaintyNoiseFloor ?? 0)}`,
          `Meaningful: ${optimizer?.meaningful ? "yes" : "no"}`,
          `Verdict: ${optimizer?.verdict ?? "Unavailable"}`,
          `Calculation: ${optimizer?.uncertaintyCalculation ?? "Unavailable"}`,
          `Top planning risk: ${context.decisionSupport.risks[0]?.message ?? "No material risk detected"}`,
          `Top planning opportunity: ${context.decisionSupport.opportunities[0]?.message ?? "No material opportunity detected"}`,
        ]
      : []),
    "",
    "Risks",
    ...insights.risks
      .slice(0, 4)
      .map((item) => `- ${item.title}: ${item.description} Mitigation: ${item.mitigation}`),
    "",
    "Opportunities",
    ...insights.growthOpportunities
      .slice(0, 4)
      .map((item) => `- ${item.title}: ${item.description} Upside: ${item.expectedImpact}`),
    "",
    "Top Recommended Actions",
    ...insights.actionPlan.slice(0, 3).map((item) => `- ${item.action} KPI: ${item.kpi}`),
    "",
    "AI and Causal Evidence",
    `AI mode: ${insights.provenance?.mode ?? "metadata unavailable"}`,
    `Network used for result: ${insights.provenance?.networkUsedForResult ? "yes" : "no"}`,
    "Causal limitation: observational evidence supports testable hypotheses, not randomized incrementality proof.",
    "Model limitations: future demand, promotions, auction dynamics and tracking changes can move outcomes outside the planning range.",
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ForecastIQ_Executive_Brief_${today()}.txt`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function writeBullets(doc: jsPDF, items: string[], yStart: number) {
  let y = yStart;
  doc.setFontSize(10);
  for (const item of items.length ? items : ["No recommendation available."]) {
    const lines = doc.splitTextToSize(`- ${item}`, 170);
    doc.text(lines, 18, y);
    y += lines.length * 6 + 4;
  }
}

function addFooter(doc: jsPDF) {
  const pageCount = doc.getNumberOfPages();
  for (let page = 1; page <= pageCount; page += 1) {
    doc.setPage(page);
    doc.setFontSize(8);
    doc.setTextColor(100);
    doc.text("ForecastIQ - Confidential planning brief", 18, 286);
  }
  doc.setTextColor(0);
}
