import type { InsightsResponse } from "@/lib/backend-api";

type ExecutiveReportSummary = {
  totalRevenue: number;
  totalSpend: number;
  avgRoas: number;
  forecast30dRevenue: number;
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

const pct = (value: number) => `${value.toFixed(1)}%`;
const roas = (value: number) => `${value.toFixed(2)}x`;

export function exportExecutivePdfReport(
  summary: ExecutiveReportSummary,
  insights: InsightsResponse,
) {
  const report = window.open("", "_blank", "noopener,noreferrer,width=1100,height=800");
  if (!report) {
    throw new Error("Popup blocked. Allow popups to export the executive PDF report.");
  }

  report.document.write(buildReportHtml(summary, insights));
  report.document.close();
  report.focus();
  setTimeout(() => report.print(), 250);
}

function buildReportHtml(summary: ExecutiveReportSummary, insights: InsightsResponse) {
  const channelRows = summary.channels
    .map(
      (channel) => `
        <tr>
          <td>${escapeHtml(channel.name)}</td>
          <td>${currency(channel.revenue)}</td>
          <td>${currency(channel.spend)}</td>
          <td>${roas(channel.roas)}</td>
          <td>${currency(channel.forecast30dRevenue)}</td>
          <td>${roas(channel.forecast30dRoas)}</td>
        </tr>`,
    )
    .join("");

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>ForecastIQ Executive Report</title>
    <style>
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 36px;
        color: #0f172a;
        background: #f8fafc;
        font-family: Inter, Arial, sans-serif;
      }
      h1, h2, h3 { margin: 0; color: #020617; }
      h1 { font-size: 30px; letter-spacing: -0.02em; }
      h2 { margin-top: 28px; font-size: 18px; }
      p { line-height: 1.55; }
      .meta { margin-top: 6px; color: #64748b; font-size: 12px; }
      .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 22px; }
      .card {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px;
      }
      .label { color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
      .value { margin-top: 6px; font-size: 22px; font-weight: 800; }
      .section {
        margin-top: 18px;
        background: #fff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 18px;
        break-inside: avoid;
      }
      table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
      th, td { border-bottom: 1px solid #e2e8f0; padding: 8px; text-align: left; }
      th { color: #64748b; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
      ul { margin: 10px 0 0; padding-left: 18px; }
      li { margin: 6px 0; line-height: 1.45; }
      @media print {
        body { background: #fff; padding: 24px; }
        .section, .card { box-shadow: none; }
      }
    </style>
  </head>
  <body>
    <h1>ForecastIQ Executive Report</h1>
    <div class="meta">Generated ${new Date().toLocaleString()} · NetElixir AIgnition 3.0</div>

    <div class="grid">
      ${metric("Total Revenue", currency(summary.totalRevenue))}
      ${metric("Total Spend", currency(summary.totalSpend))}
      ${metric("Average ROAS", roas(summary.avgRoas))}
      ${metric("90 Day Forecast", currency(summary.forecast90dRevenue ?? 0))}
    </div>

    <div class="section">
      <h2>Executive Summary</h2>
      <p>${escapeHtml(insights.executiveSummary)}</p>
    </div>

    <div class="section">
      <h2>Business Impact</h2>
      <p>Revenue trend: ${pct(summary.revenueTrendPct)}. ROAS trend: ${pct(summary.roasTrendPct)}. Thirty day forecast: ${currency(summary.forecast30dRevenue)}.</p>
      <table>
        <thead>
          <tr>
            <th>Channel</th>
            <th>Revenue</th>
            <th>Spend</th>
            <th>ROAS</th>
            <th>30d Forecast</th>
            <th>30d ROAS</th>
          </tr>
        </thead>
        <tbody>${channelRows}</tbody>
      </table>
    </div>

    ${listSection("Revenue Drivers", insights.revenueDrivers?.map((item) => `${item.title}: ${item.detail}`) ?? [])}
    ${listSection("Risks", insights.risks?.map((item) => `${item.title}: ${item.description} Mitigation: ${item.mitigation}`) ?? [])}
    ${listSection("Opportunities", insights.growthOpportunities?.map((item) => `${item.title}: ${item.description} Impact: ${item.expectedImpact}`) ?? [])}
    ${listSection("Recommended Actions", insights.actionPlan?.map((item) => `${item.timeline} - ${item.action} KPI: ${item.kpi}`) ?? [])}
  </body>
</html>`;
}

function metric(label: string, value: string) {
  return `<div class="card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div></div>`;
}

function listSection(title: string, items: string[]) {
  return `<div class="section"><h2>${escapeHtml(title)}</h2><ul>${items
    .slice(0, 6)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</ul></div>`;
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
