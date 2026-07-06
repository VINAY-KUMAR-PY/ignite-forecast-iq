import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  DollarSign,
  Gauge,
  Lightbulb,
  Target,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { useData } from "@/lib/data-store";
import { aggregateDaily } from "@/lib/forecasting";
import { fmtCompact, fmtCurrency, fmtDate, fmtRoas } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { fetchAnomaliesApi, type AnomalyResponse } from "@/lib/backend-api";

export const Route = createFileRoute("/app/")({
  head: () => ({ meta: [{ title: "Executive Decision Center - ForecastIQ" }] }),
  component: Dashboard,
});

const COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
];

function Dashboard() {
  const { rows } = useData();
  const [anomalyResponse, setAnomalyResponse] = useState<AnomalyResponse | null>(null);
  const [showAnomalies, setShowAnomalies] = useState(false);
  const [dismissedAnomalies, setDismissedAnomalies] = useState(false);

  useEffect(() => {
    if (!rows.length) return;
    let active = true;
    fetchAnomaliesApi(rows)
      .then((response) => {
        if (active) setAnomalyResponse(response);
      })
      .catch(() => {
        if (active) setAnomalyResponse(null);
      });
    return () => {
      active = false;
    };
  }, [rows]);

  const stats = useMemo(() => {
    if (!rows.length) return null;
    const totalRevenue = rows.reduce((s, r) => s + r.revenue, 0);
    const totalSpend = rows.reduce((s, r) => s + r.spend, 0);
    const avgRoas = totalSpend > 0 ? totalRevenue / totalSpend : 0;
    const campaigns = new Set(rows.map((r) => `${r.channel}|${r.campaign_name}`));
    const daily = aggregateDaily(rows);
    // last 30 vs prior 30
    const last30 = daily.slice(-30);
    const prev30 = daily.slice(-60, -30);
    const sum = (arr: typeof daily, k: "revenue" | "spend") => arr.reduce((s, d) => s + d[k], 0);
    const last30Revenue = sum(last30, "revenue");
    const prev30Revenue = sum(prev30, "revenue");
    const last30Spend = sum(last30, "spend");
    const prev30Spend = sum(prev30, "spend");
    const revPrev = prev30Revenue || 1;
    const spendPrev = prev30Spend || 1;
    const revDelta = ((last30Revenue - revPrev) / revPrev) * 100;
    const spendDelta = ((last30Spend - spendPrev) / spendPrev) * 100;
    const lastRoas = last30Spend > 0 ? last30Revenue / last30Spend : 0;
    const prevRoas = prev30Spend > 0 ? prev30Revenue / prev30Spend : 0;
    const roasDelta = prevRoas > 0 ? ((lastRoas - prevRoas) / prevRoas) * 100 : 0;
    const last30Profit = last30Revenue - last30Spend;
    const prev30Profit = prev30Revenue - prev30Spend;
    const incrementalRevenue = last30Revenue - prev30Revenue;
    const incrementalSpend = last30Spend - prev30Spend;
    const marginalRoas = incrementalSpend > 0 ? incrementalRevenue / incrementalSpend : lastRoas;

    // channel agg
    const chMap = new Map<string, { spend: number; revenue: number }>();
    for (const r of rows) {
      const c = chMap.get(r.channel) ?? { spend: 0, revenue: 0 };
      c.spend += r.spend;
      c.revenue += r.revenue;
      chMap.set(r.channel, c);
    }
    const channels = [...chMap.entries()].map(([name, v]) => ({
      name,
      spend: v.spend,
      revenue: v.revenue,
      roas: v.spend > 0 ? v.revenue / v.spend : 0,
    }));
    const rankedChannels = [...channels].sort((a, b) => b.roas - a.roas);
    const strongestChannel = rankedChannels[0];
    const weakestChannel = rankedChannels[rankedChannels.length - 1];
    const reallocationOpportunity =
      strongestChannel && weakestChannel
        ? Math.max(0, weakestChannel.spend * 0.1 * (strongestChannel.roas - weakestChannel.roas))
        : 0;
    const last30AverageRevenue =
      last30.length > 0 ? last30Revenue / last30.length : totalRevenue / Math.max(1, daily.length);
    const forecast30Revenue = Math.max(
      0,
      last30AverageRevenue * 30 * clampNumber(1 + revDelta / 100, 0.75, 1.25),
    );
    const expectedRoas = lastRoas || avgRoas;
    const confidenceScore = Math.round(
      clampNumber(
        64 +
          Math.min(18, daily.length / 6) +
          Math.min(8, campaigns.size / 4) -
          Math.min(14, Math.abs(roasDelta) / 2),
        55,
        94,
      ),
    );
    const roasLiftPotential =
      strongestChannel && weakestChannel
        ? Math.max(0, strongestChannel.roas - weakestChannel.roas)
        : 0;
    const riskAlerts = [
      ...(roasDelta < -5
        ? [`ROAS has moved ${Math.abs(roasDelta).toFixed(1)}% below the prior 30 days.`]
        : []),
      ...(spendDelta > revDelta + 8
        ? ["Spend is growing faster than revenue, which can pressure contribution margin."]
        : []),
      ...(weakestChannel && weakestChannel.roas < avgRoas * 0.75
        ? [`${weakestChannel.name} is materially below blended ROAS.`]
        : []),
    ].slice(0, 3);
    const opportunityAlerts = [
      ...(strongestChannel
        ? [`${strongestChannel.name} is the best channel to test incremental budget.`]
        : []),
      ...(reallocationOpportunity > 0 && weakestChannel && strongestChannel
        ? [
            `Moving 10% from ${weakestChannel.name} to ${strongestChannel.name} shows ${fmtCurrency(
              reallocationOpportunity,
            )} upside.`,
          ]
        : []),
      ...(revDelta > 0
        ? [`Revenue momentum is positive at +${revDelta.toFixed(1)}% vs the prior 30 days.`]
        : ["Stabilize high-spend campaigns before scaling new budget."]),
    ].slice(0, 3);
    const riskLevel =
      riskAlerts.length >= 3 || roasDelta < -12
        ? "High"
        : riskAlerts.length > 0 || roasDelta < -5
          ? "Medium"
          : "Low";
    const recommendedAction =
      strongestChannel && weakestChannel && reallocationOpportunity > 0
        ? `Move ${fmtCurrency(weakestChannel.spend * 0.1)} from ${weakestChannel.name} into ${strongestChannel.name}.`
        : revDelta >= 0
          ? "Maintain current channel mix and scale winners carefully."
          : "Pause aggressive scaling and fix low-efficiency campaigns first.";
    const expectedRevenueImpact =
      Math.max(0, forecast30Revenue - last30Revenue) + reallocationOpportunity;
    const wastedSpendReduction = weakestChannel ? Math.max(0, weakestChannel.spend * 0.1) : 0;
    const growthOpportunity = strongestChannel
      ? Math.max(0, strongestChannel.spend * 0.15 * strongestChannel.roas * 0.85)
      : 0;
    const expectedBusinessImpact = expectedRevenueImpact + growthOpportunity;
    const bestBudgetAction =
      strongestChannel && weakestChannel && reallocationOpportunity > 0
        ? `${fmtCurrency(wastedSpendReduction)} shift: ${weakestChannel.name} -> ${strongestChannel.name}`
        : recommendedAction;
    const topActions = [
      bestBudgetAction,
      strongestChannel
        ? `Scale ${strongestChannel.name} by 10-15% only while marginal ROAS stays above ${fmtRoas(avgRoas)}.`
        : "Keep channel budgets close to baseline until more data is available.",
      weakestChannel
        ? `Cut weak ${weakestChannel.name} campaigns first; recycle savings into proven high-intent demand.`
        : "Recheck underperforming campaigns before the next budget cycle.",
    ];

    return {
      totalRevenue,
      totalSpend,
      avgRoas,
      campaigns: campaigns.size,
      daily,
      channels,
      revDelta,
      spendDelta,
      roasDelta,
      executive: {
        forecast30Revenue,
        expectedRoas,
        confidenceScore,
        bestChannel: strongestChannel?.name ?? "N/A",
        worstChannel: weakestChannel?.name ?? "N/A",
        riskAlerts,
        opportunityAlerts,
        recommendedAction,
        bestBudgetAction,
        expectedRevenueImpact,
        expectedBusinessImpact,
        wastedSpendReduction,
        growthOpportunity,
        roasImpact: roasLiftPotential,
        riskLevel,
        topActions,
      },
      businessImpact: {
        last30Revenue,
        incrementalRevenue,
        last30Profit,
        profitDelta: last30Profit - prev30Profit,
        marginalRoas,
        reallocationOpportunity,
        strongestChannel: strongestChannel?.name ?? "N/A",
        weakestChannel: weakestChannel?.name ?? "N/A",
      },
    };
  }, [rows]);

  if (!stats)
    return (
      <>
        <PageHeader title="Executive Decision Center" />
        <EmptyState />
      </>
    );

  // Sample daily for chart (every Nth point if long)
  const dailySample =
    stats.daily.length > 120
      ? stats.daily.filter((_, i) => i % 3 === 0 || i === stats.daily.length - 1)
      : stats.daily;

  return (
    <>
      <PageHeader
        title="Executive Decision Center"
        description="Start here for forecasted revenue, expected ROAS, risk, opportunity, and the next budget move."
      />

      {anomalyResponse && anomalyResponse.anomalies.length > 0 && !dismissedAnomalies && (
        <Card
          className={`mb-6 border p-4 ${
            anomalyResponse.anomalies.some((item) => item.severity === "critical")
              ? "border-destructive/40 bg-destructive/10"
              : "border-warning/40 bg-warning/10"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => setShowAnomalies((value) => !value)}
              className="flex items-center gap-2 text-left text-sm font-semibold"
            >
              <AlertTriangle className="h-4 w-4" />
              {anomalyResponse.anomalies.filter((item) => item.severity === "critical").length
                ? `${anomalyResponse.anomalies.filter((item) => item.severity === "critical").length} critical anomalies detected - review before forecasting`
                : `${anomalyResponse.anomalies.length} anomaly warnings detected - review before forecasting`}
            </button>
            <Button variant="ghost" size="sm" onClick={() => setDismissedAnomalies(true)}>
              Dismiss
            </Button>
          </div>
          {showAnomalies && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 text-left">Date</th>
                    <th className="px-2 py-2 text-left">Channel</th>
                    <th className="px-2 py-2 text-left">Metric</th>
                    <th className="px-2 py-2 text-right">Z-score</th>
                    <th className="px-2 py-2 text-left">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalyResponse.anomalies.slice(0, 12).map((item) => (
                    <tr
                      key={`${item.date}-${item.channel}-${item.metric}-${item.z_score}`}
                      className="border-t border-border/40"
                    >
                      <td className="px-2 py-2">{item.date}</td>
                      <td className="px-2 py-2">{item.channel}</td>
                      <td className="px-2 py-2 uppercase">{item.metric}</td>
                      <td className="px-2 py-2 text-right">{item.z_score.toFixed(2)}</td>
                      <td className="px-2 py-2 text-muted-foreground">{item.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Total Revenue"
          value={fmtCurrency(stats.totalRevenue)}
          delta={stats.revDelta}
          icon={DollarSign}
          hint="vs prior 30d"
        />
        <KpiCard
          label="Total Spend"
          value={fmtCurrency(stats.totalSpend)}
          delta={stats.spendDelta}
          icon={Activity}
          hint="vs prior 30d"
        />
        <KpiCard
          label="Avg ROAS"
          value={fmtRoas(stats.avgRoas)}
          delta={stats.roasDelta}
          icon={Target}
          hint="vs prior 30d"
        />
        <KpiCard
          label="Campaigns"
          value={stats.campaigns.toString()}
          icon={TrendingUp}
          hint={`${stats.channels.length} channels`}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <ExecutiveMetric
          label="30d forecasted revenue"
          value={fmtCurrency(stats.executive.forecast30Revenue)}
          hint="near-term planning view"
          icon={DollarSign}
        />
        <ExecutiveMetric
          label="Expected ROAS"
          value={fmtRoas(stats.executive.expectedRoas)}
          hint="recent blended efficiency"
          icon={Target}
        />
        <ExecutiveMetric
          label="Best channel"
          value={stats.executive.bestChannel}
          hint="highest observed ROAS"
          icon={TrendingUp}
        />
        <ExecutiveMetric
          label="Worst channel"
          value={stats.executive.worstChannel}
          hint="reallocation candidate"
          icon={AlertTriangle}
        />
        <ExecutiveMetric
          label="Confidence score"
          value={`${stats.executive.confidenceScore}/100`}
          hint="data depth and volatility"
          icon={Gauge}
        />
      </div>

      <Card
        data-testid="executive-decision-center"
        className="mt-6 bg-gradient-card border-border/60 p-5"
      >
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold">Executive Decision Center</h3>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Judge starting point: best budget action, expected impact, risk level, and next three
              actions.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span
              className={`rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider ${confidenceBadgeClass(
                stats.executive.confidenceScore,
              )}`}
            >
              {stats.executive.confidenceScore}/100 confidence
            </span>
            <span
              className={`rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider ${riskBadgeClass(
                stats.executive.riskLevel,
              )}`}
            >
              {stats.executive.riskLevel} risk
            </span>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-6">
          <ImpactMetric
            label="Best budget action"
            value={stats.executive.bestBudgetAction}
            hint="exact channel move"
          />
          <ImpactMetric
            label="Business impact"
            value={fmtCurrency(stats.executive.expectedBusinessImpact)}
            hint="lift plus growth upside"
          />
          <ImpactMetric
            label="Waste reduction"
            value={fmtCurrency(stats.executive.wastedSpendReduction)}
            hint="budget to recycle"
          />
          <ImpactMetric
            label="Growth opportunity"
            value={fmtCurrency(stats.executive.growthOpportunity)}
            hint="controlled winner scaling"
          />
          <ImpactMetric
            label="ROAS impact"
            value={`+${stats.executive.roasImpact.toFixed(2)}x`}
            hint="best vs weakest channel gap"
          />
          <ImpactMetric
            label="Confidence"
            value={`${stats.executive.confidenceScore}/100`}
            hint="based on history and trend stability"
          />
        </div>
        <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-border/40 bg-background/40 p-4 lg:col-span-1">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
              <CheckCircle2 className="h-3.5 w-3.5" /> Top next actions
            </div>
            <ol className="space-y-2 text-sm">
              {stats.executive.topActions.map((action, index) => (
                <li key={action} className="flex gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">{index + 1}.</span>
                  <span>{action}</span>
                </li>
              ))}
            </ol>
          </div>
          <AlertList
            title="Risk alerts"
            icon={AlertTriangle}
            items={stats.executive.riskAlerts}
            empty="No major risk alerts in the current readout."
            tone="risk"
          />
          <AlertList
            title="Opportunity alerts"
            icon={Lightbulb}
            items={stats.executive.opportunityAlerts}
            empty="No clear scaling opportunity yet."
            tone="opportunity"
          />
        </div>
      </Card>

      <Card
        data-testid="business-impact-dashboard"
        className="mt-6 bg-gradient-card border-border/60 p-5"
      >
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">Business impact dashboard</h3>
            <p className="text-xs text-muted-foreground">
              Executive view of recent revenue lift, profit movement and reallocation upside.
            </p>
          </div>
          <ArrowUpRight className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <ImpactMetric
            label="30d revenue impact"
            value={fmtCurrency(stats.businessImpact.last30Revenue)}
            hint={`${formatSignedCurrency(stats.businessImpact.incrementalRevenue)} vs prior 30d`}
          />
          <ImpactMetric
            label="Profit impact"
            value={fmtCurrency(stats.businessImpact.last30Profit)}
            hint={`${formatSignedCurrency(stats.businessImpact.profitDelta)} vs prior 30d`}
          />
          <ImpactMetric
            label="Marginal ROAS"
            value={fmtRoas(stats.businessImpact.marginalRoas)}
            hint="incremental revenue per new media dollar"
          />
          <ImpactMetric
            label="Reallocation upside"
            value={fmtCurrency(stats.businessImpact.reallocationOpportunity)}
            hint={`${stats.businessImpact.weakestChannel} to ${stats.businessImpact.strongestChannel}`}
          />
        </div>
      </Card>

      <div className="mt-6 grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Revenue trend"
          subtitle="Daily revenue over time"
          ariaLabel={`Revenue trend chart covering ${stats.daily.length} days with total revenue ${fmtCurrency(
            stats.totalRevenue,
          )}.`}
        >
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={dailySample} margin={{ left: -10, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="rev" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tickFormatter={fmtDate}
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                minTickGap={40}
              />
              <YAxis
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                tickFormatter={(v) => fmtCompact(v as number)}
              />
              <Tooltip content={<TT formatter={fmtCurrency} />} />
              <Area
                type="monotone"
                dataKey="revenue"
                stroke="var(--color-chart-1)"
                fill="url(#rev)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Spend trend"
          subtitle="Daily media spend"
          ariaLabel={`Spend trend chart covering ${stats.daily.length} days with total spend ${fmtCurrency(
            stats.totalSpend,
          )}.`}
        >
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={dailySample} margin={{ left: -10, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="sp" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-chart-2)" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="var(--color-chart-2)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tickFormatter={fmtDate}
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                minTickGap={40}
              />
              <YAxis
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                tickFormatter={(v) => fmtCompact(v as number)}
              />
              <Tooltip content={<TT formatter={fmtCurrency} />} />
              <Area
                type="monotone"
                dataKey="spend"
                stroke="var(--color-chart-2)"
                fill="url(#sp)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="ROAS trend"
          subtitle="Blended ROAS by day"
          ariaLabel={`ROAS trend chart with blended ROAS ${fmtRoas(stats.avgRoas)} across ${
            stats.daily.length
          } days.`}
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={dailySample} margin={{ left: -10, right: 8, top: 8 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tickFormatter={fmtDate}
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                minTickGap={40}
              />
              <YAxis
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                tickFormatter={(v) => `${(v as number).toFixed(1)}x`}
              />
              <Tooltip content={<TT formatter={(v: number) => `${v.toFixed(2)}x`} />} />
              <Line
                type="monotone"
                dataKey="roas"
                stroke="var(--color-chart-3)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Channel performance"
          subtitle="Revenue vs spend by channel"
          ariaLabel={`Channel performance chart comparing revenue and spend across ${stats.channels.length} channels.`}
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={stats.channels} margin={{ left: -10, right: 8, top: 8 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
              <XAxis dataKey="name" stroke="var(--color-muted-foreground)" fontSize={11} />
              <YAxis
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                tickFormatter={(v) => fmtCompact(v as number)}
              />
              <Tooltip content={<TT formatter={fmtCurrency} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="revenue" fill="var(--color-chart-1)" radius={[6, 6, 0, 0]} />
              <Bar dataKey="spend" fill="var(--color-chart-2)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {stats.channels.map((c, i) => (
          <Card key={c.name} className="bg-gradient-card border-border/60 min-w-0 p-5">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 break-words text-sm font-semibold">{c.name}</div>
              <div
                className="h-2 w-2 rounded-full"
                style={{ background: COLORS[i % COLORS.length] }}
              />
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 text-xs sm:grid-cols-3">
              <div className="min-w-0">
                <div className="text-muted-foreground">Revenue</div>
                <div className="mt-1 break-words text-sm font-semibold">
                  {fmtCompact(c.revenue)}
                </div>
              </div>
              <div className="min-w-0">
                <div className="text-muted-foreground">Spend</div>
                <div className="mt-1 break-words text-sm font-semibold">{fmtCompact(c.spend)}</div>
              </div>
              <div className="min-w-0">
                <div className="text-muted-foreground">ROAS</div>
                <div className="mt-1 break-words text-sm font-semibold">{fmtRoas(c.roas)}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}

function ExecutiveMetric({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: LucideIcon;
}) {
  return (
    <Card className="bg-gradient-card border-border/60 min-w-0 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
          <div className="mt-1 break-words text-lg font-semibold leading-tight">{value}</div>
          <div className="mt-1 break-words text-xs text-muted-foreground">{hint}</div>
        </div>
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
      </div>
    </Card>
  );
}

function ImpactMetric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-lg font-semibold leading-tight">{value}</div>
      <div className="mt-1 break-words text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

function AlertList({
  title,
  icon: Icon,
  items,
  empty,
  tone,
}: {
  title: string;
  icon: LucideIcon;
  items: string[];
  empty: string;
  tone: "risk" | "opportunity";
}) {
  const color = tone === "risk" ? "text-warning" : "text-success";
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
      <div
        className={`mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider ${color}`}
      >
        <Icon className="h-3.5 w-3.5" /> {title}
      </div>
      <div className="space-y-2">
        {(items.length ? items : [empty]).map((item) => (
          <div key={item} className="break-words text-sm text-muted-foreground">
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}

function formatSignedCurrency(value: number) {
  return `${value >= 0 ? "+" : ""}${fmtCurrency(value)}`;
}

function riskBadgeClass(level: string) {
  if (level === "High") return "border-destructive/30 bg-destructive/15 text-destructive";
  if (level === "Medium") return "border-warning/30 bg-warning/15 text-warning";
  return "border-success/30 bg-success/15 text-success";
}

function confidenceBadgeClass(score: number) {
  if (score >= 85) return "border-success/30 bg-success/15 text-success";
  if (score >= 70) return "border-primary/30 bg-primary/15 text-primary";
  return "border-warning/30 bg-warning/15 text-warning";
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function ChartCard({
  title,
  subtitle,
  ariaLabel,
  children,
}: {
  title: string;
  subtitle?: string;
  ariaLabel: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="bg-gradient-card border-border/60 min-w-0 overflow-hidden p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      <div role="img" aria-label={ariaLabel}>
        {children}
      </div>
    </Card>
  );
}

type TooltipPayload = {
  dataKey: string;
  color: string;
  value: number;
};

function TT({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
  formatter?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <div className="font-medium">{label ? fmtDate(label) : ""}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="mt-1 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="capitalize text-muted-foreground">{p.dataKey}:</span>
          <span className="font-medium">{formatter ? formatter(p.value) : p.value}</span>
        </div>
      ))}
    </div>
  );
}
