import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import type { InsightsResponse } from "@/lib/backend-api";

type ExecutiveReportSummary = {
  totalRevenue: number;
  totalSpend: number;
  avgRoas: number;
  forecast30dRevenue: number;
  forecast60dRevenue?: number;
  forecast90dRevenue?: number;
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
): void {
  try {
    const doc = new jsPDF();
    addFooter(doc);

    doc.setFontSize(24);
    doc.text("ForecastIQ Executive Briefing", 18, 34);
    doc.setFontSize(11);
    doc.text(`Date: ${today()}`, 18, 48);
    doc.text("Client: Demo ecommerce account", 18, 56);
    doc.text("Prepared for: NetElixir AIgnition 3.0 Grand Finale", 18, 64);
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

    doc.save(`ForecastIQ_Executive_Brief_${today()}.pdf`);
  } catch {
    downloadTextReport(summary, insights);
  }
}

function downloadTextReport(summary: ExecutiveReportSummary, insights: InsightsResponse) {
  const primaryRecommendation =
    insights.actionPlan?.[0]?.action ??
    insights.budgetAllocation?.[0]?.rationale ??
    "Review budget scenarios and monitor forecast interval width before changing spend.";
  const lines = [
    "ForecastIQ Executive Briefing",
    `Generated: ${timestamp()}`,
    "",
    "Executive Summary",
    insights.executiveSummary,
    "",
    "Forecast Summary",
    `30-day revenue forecast: ${currency(summary.forecast30dRevenue)}`,
    `60-day revenue forecast: ${currency(summary.forecast60dRevenue ?? 0)}`,
    `90-day revenue forecast: ${currency(summary.forecast90dRevenue ?? 0)}`,
    `Average ROAS: ${roas(summary.avgRoas)}`,
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
    doc.text("Powered by ForecastIQ - Confidential", 18, 286);
  }
  doc.setTextColor(0);
}
