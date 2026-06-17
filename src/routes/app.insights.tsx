import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Brain,
  Lightbulb,
  ListChecks,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useData } from "@/lib/data-store";
import { aggregateDaily, forecastRevenue, forecastRoas } from "@/lib/forecasting";
import { generateInsights, type InsightsResponse } from "@/lib/ai-insights.functions";
import { fmtCurrency, fmtPct, fmtRoas } from "@/lib/format";
import type { CampaignRow } from "@/lib/types";

export const Route = createFileRoute("/app/insights")({
  head: () => ({ meta: [{ title: "AI Insights · ForecastIQ" }] }),
  component: InsightsPage,
});

const CHANNELS = ["Google Ads", "Meta Ads", "Microsoft Ads"];

function InsightsPage() {
  const { rows } = useData();
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const summary = useMemo(() => buildSummary(rows), [rows]);

  if (!rows.length || !summary)
    return (
      <>
        <PageHeader title="AI insights" />
        <EmptyState />
      </>
    );

  async function run() {
    setLoading(true);
    try {
      const res = await generateInsights(summary!);
      setInsights(res);
      toast.success("Executive briefing generated");
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Failed to generate insights");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="AI executive insights"
        description="Board-ready briefing combining historical performance with the XGBoost forecasting model."
        actions={
          <Button variant="hero" onClick={run} disabled={loading}>
            <Sparkles className="mr-2 h-4 w-4" />
            {loading ? "Analyzing…" : insights ? "Regenerate" : "Generate insights"}
          </Button>
        }
      />

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <Stat label="Revenue (all time)" value={fmtCurrency(summary.totalRevenue)} />
        <Stat label="Avg ROAS" value={fmtRoas(summary.avgRoas)} delta={summary.roasTrendPct} />
        <Stat label="30d revenue forecast" value={fmtCurrency(summary.forecast30dRevenue)} />
        <Stat label="90d revenue forecast" value={fmtCurrency(summary.forecast90dRevenue ?? 0)} />
      </div>

      {!insights && !loading && (
        <Card className="bg-gradient-card border-border/60 p-10 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-gradient-brand shadow-glow">
            <Brain className="h-5 w-5 text-primary-foreground" />
          </div>
          <h3 className="mt-4 text-lg font-semibold">Ready when you are</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Click <em>Generate insights</em> to produce a CMO-level briefing with revenue drivers,
            channel &amp; campaign analysis, budget allocation, risks and growth opportunities.
          </p>
        </Card>
      )}

      {loading && (
        <Card className="bg-gradient-card border-border/60 p-10 text-center">
          <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="mt-4 text-sm text-muted-foreground">
            Analyzing {rows.length.toLocaleString()} rows across {summary.channels.length} channels
            and {summary.totalCampaigns} campaigns…
          </p>
        </Card>
      )}

      {insights && (
        <div className="grid gap-6">
          <Card className="bg-gradient-hero border-border/60 p-6">
            <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-primary-glow">
              <Brain className="h-4 w-4" /> Executive summary
            </div>
            <p className="mt-3 text-base leading-relaxed">{insights.executiveSummary}</p>
          </Card>

          {/* Revenue drivers */}
          <SectionCard icon={TrendingUp} title="Revenue drivers" accent="success">
            <div className="grid gap-3 md:grid-cols-2">
              {insights.revenueDrivers?.map((d, i) => (
                <div key={i} className="rounded-lg border border-border/40 bg-background/40 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <h4 className="text-sm font-semibold">{d.title}</h4>
                    {d.metric && (
                      <span className="rounded-full bg-success/15 px-2 py-0.5 text-[11px] font-medium text-success">
                        {d.metric}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{d.detail}</p>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Channel performance */}
          <SectionCard icon={Target} title="Channel performance analysis" accent="primary">
            <div className="grid gap-3 md:grid-cols-3">
              {insights.channelPerformance?.map((c, i) => (
                <div key={i} className="rounded-lg border border-border/40 bg-background/40 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold">{c.channel}</h4>
                    <VerdictBadge verdict={c.verdict} />
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{c.insight}</p>
                  <div className="mt-3 rounded-md bg-primary/10 px-3 py-2 text-xs">
                    <span className="font-medium text-primary">Action: </span>
                    <span className="text-foreground/90">{c.recommendation}</span>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Campaign performance */}
          <SectionCard icon={Sparkles} title="Campaign performance analysis" accent="primary">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-success">
                  <TrendingUp className="h-3.5 w-3.5" /> Top performers
                </div>
                <ul className="space-y-2">
                  {insights.campaignPerformance?.top?.map((c, i) => (
                    <li key={i} className="rounded-md border border-border/40 bg-background/40 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{c.name}</span>
                        <span className="text-[11px] text-muted-foreground">{c.channel}</span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{c.insight}</p>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-destructive">
                  <TrendingDown className="h-3.5 w-3.5" /> Underperformers
                </div>
                <ul className="space-y-2">
                  {insights.campaignPerformance?.bottom?.map((c, i) => (
                    <li key={i} className="rounded-md border border-border/40 bg-background/40 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{c.name}</span>
                        <span className="text-[11px] text-muted-foreground">{c.channel}</span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        <span className="font-medium text-destructive">Issue: </span>
                        {c.issue}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">Action: </span>
                        {c.action}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </SectionCard>

          {/* Budget allocation */}
          <SectionCard icon={Wallet} title="Budget allocation strategy" accent="success">
            <div className="space-y-3">
              {insights.budgetAllocation?.map((b, i) => {
                const delta = b.recommendedSharePct - b.currentSharePct;
                return (
                  <div key={i} className="rounded-lg border border-border/40 bg-background/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-semibold">{b.channel}</span>
                        <span className="text-xs text-muted-foreground">
                          {fmtPct(b.currentSharePct / 100)} →{" "}
                          <span className="font-medium text-foreground">
                            {fmtPct(b.recommendedSharePct / 100)}
                          </span>
                        </span>
                      </div>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          delta > 0
                            ? "bg-success/15 text-success"
                            : delta < 0
                              ? "bg-destructive/15 text-destructive"
                              : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {delta >= 0 ? "+" : ""}
                        {delta.toFixed(0)} pts
                      </span>
                    </div>
                    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${Math.min(100, Math.max(0, b.recommendedSharePct))}%` }}
                      />
                    </div>
                    <p className="mt-3 text-xs text-muted-foreground">{b.rationale}</p>
                    <p className="mt-1 text-xs">
                      <span className="font-medium text-success">Expected impact: </span>
                      <span className="text-muted-foreground">{b.expectedImpact}</span>
                    </p>
                  </div>
                );
              })}
            </div>
          </SectionCard>

          {/* Risks */}
          <SectionCard icon={AlertTriangle} title="Risk analysis" accent="destructive">
            <div className="grid gap-3 md:grid-cols-2">
              {insights.risks?.map((r, i) => (
                <div key={i} className="rounded-lg border border-border/40 bg-background/40 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold">{r.title}</h4>
                    <SeverityBadge severity={r.severity} />
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{r.description}</p>
                  <div className="mt-2 rounded-md bg-warning/10 px-3 py-2 text-xs">
                    <span className="font-medium text-warning">Mitigation: </span>
                    <span className="text-foreground/90">{r.mitigation}</span>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Growth opportunities */}
          <SectionCard icon={Lightbulb} title="Growth opportunities" accent="primary">
            <div className="grid gap-3 md:grid-cols-2">
              {insights.growthOpportunities?.map((g, i) => (
                <div key={i} className="rounded-lg border border-border/40 bg-background/40 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold">{g.title}</h4>
                    <EffortBadge effort={g.effort} />
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{g.description}</p>
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-success">
                    <ArrowUpRight className="h-3.5 w-3.5" />
                    <span>{g.expectedImpact}</span>
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Action plan */}
          <SectionCard icon={ListChecks} title="Action plan" accent="success">
            <div className="space-y-3">
              {insights.actionPlan?.map((item, i) => (
                <div key={i} className="rounded-lg border border-border/40 bg-background/40 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <PriorityBadge priority={item.priority} />
                      <span className="text-xs text-muted-foreground">{item.timeline}</span>
                    </div>
                    <span className="text-xs font-medium text-muted-foreground">{item.owner}</span>
                  </div>
                  <p className="mt-3 text-sm">{item.action}</p>
                  <p className="mt-2 text-xs">
                    <span className="font-medium text-success">KPI: </span>
                    <span className="text-muted-foreground">{item.kpi}</span>
                  </p>
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      )}
    </>
  );
}

// ---------- helpers ----------

function buildSummary(rows: CampaignRow[]) {
  if (!rows.length) return null;
  const totalRevenue = rows.reduce((s, r) => s + r.revenue, 0);
  const totalSpend = rows.reduce((s, r) => s + r.spend, 0);
  const avgRoas = totalSpend > 0 ? totalRevenue / totalSpend : 0;
  const campaignKeys = new Set(rows.map((r) => `${r.channel}|${r.campaign_name}`));

  // Per-channel aggregates + trend + per-channel 30d forecast
  const chMap = new Map<string, { revenue: number; spend: number }>();
  for (const r of rows) {
    const c = chMap.get(r.channel) ?? { revenue: 0, spend: 0 };
    c.revenue += r.revenue;
    c.spend += r.spend;
    chMap.set(r.channel, c);
  }
  const channels = [...chMap.entries()].map(([name, v]) => {
    const chRows = rows.filter((r) => r.channel === name);
    const dailyCh = aggregateDaily(chRows);
    const last30 = dailyCh.slice(-30).reduce((s, d) => s + d.revenue, 0);
    const prev30 = dailyCh.slice(-60, -30).reduce((s, d) => s + d.revenue, 0) || 1;
    const trend = Math.round(((last30 - prev30) / prev30) * 1000) / 10;

    let fc30Rev = 0;
    let fc30Roas = 0;
    if (CHANNELS.includes(name) && dailyCh.length >= 35) {
      const fcR = forecastRevenue(chRows, 30).filter((p) => !p.historical);
      fc30Rev = Math.round(fcR.reduce((s, p) => s + p.value, 0));
      const fcRoas = forecastRoas(chRows, 30).filter((p) => !p.historical);
      fc30Roas = fcRoas.length
        ? Math.round((fcRoas.reduce((s, p) => s + p.value, 0) / fcRoas.length) * 100) / 100
        : 0;
    }

    return {
      name,
      revenue: Math.round(v.revenue),
      spend: Math.round(v.spend),
      roas: v.spend > 0 ? Math.round((v.revenue / v.spend) * 100) / 100 : 0,
      sharePct: totalRevenue > 0 ? Math.round((v.revenue / totalRevenue) * 1000) / 10 : 0,
      forecast30dRevenue: fc30Rev,
      forecast30dRoas: fc30Roas,
      revenueTrendPct: trend,
    };
  });

  // Per-campaign aggregates
  const cMap = new Map<
    string,
    { revenue: number; spend: number; conversions: number; channel: string; type: string }
  >();
  for (const r of rows) {
    const k = `${r.channel}|${r.campaign_name}`;
    const c = cMap.get(k) ?? {
      revenue: 0,
      spend: 0,
      conversions: 0,
      channel: r.channel,
      type: r.campaign_type,
    };
    c.revenue += r.revenue;
    c.spend += r.spend;
    c.conversions += r.conversions;
    cMap.set(k, c);
  }
  const campaignsArr = [...cMap.entries()].map(([k, v]) => ({
    name: k.split("|")[1],
    channel: v.channel,
    campaignType: v.type,
    revenue: Math.round(v.revenue),
    spend: Math.round(v.spend),
    conversions: Math.round(v.conversions),
    roas: v.spend > 0 ? Math.round((v.revenue / v.spend) * 100) / 100 : 0,
  }));
  const topCampaigns = [...campaignsArr].sort((a, b) => b.revenue - a.revenue).slice(0, 5);
  const bottomCampaigns = [...campaignsArr]
    .filter((c) => c.spend > 100)
    .sort((a, b) => a.roas - b.roas)
    .slice(0, 5);

  // Campaign type breakdown
  const tMap = new Map<string, { revenue: number; spend: number }>();
  for (const r of rows) {
    const t = tMap.get(r.campaign_type) ?? { revenue: 0, spend: 0 };
    t.revenue += r.revenue;
    t.spend += r.spend;
    tMap.set(r.campaign_type, t);
  }
  const campaignTypeBreakdown = [...tMap.entries()].map(([type, v]) => ({
    type,
    revenue: Math.round(v.revenue),
    spend: Math.round(v.spend),
    roas: v.spend > 0 ? Math.round((v.revenue / v.spend) * 100) / 100 : 0,
  }));

  // Overall trends
  const daily = aggregateDaily(rows);
  const last30 = daily.slice(-30).reduce((s, d) => s + d.revenue, 0);
  const prev30 = daily.slice(-60, -30).reduce((s, d) => s + d.revenue, 0) || 1;
  const revenueTrendPct = Math.round(((last30 - prev30) / prev30) * 1000) / 10;
  const last30Spend = daily.slice(-30).reduce((s, d) => s + d.spend, 0);
  const prev30Spend = daily.slice(-60, -30).reduce((s, d) => s + d.spend, 0) || 1;
  const spendTrendPct = Math.round(((last30Spend - prev30Spend) / prev30Spend) * 1000) / 10;
  const last30Roas = last30Spend > 0 ? last30 / last30Spend : 0;
  const prev30Roas = prev30Spend > 0 ? prev30 / prev30Spend : 0;
  const roasTrendPct =
    prev30Roas > 0 ? Math.round(((last30Roas - prev30Roas) / prev30Roas) * 1000) / 10 : 0;

  // Forecast horizons
  const fc90 = forecastRevenue(rows, 90).filter((p) => !p.historical);
  const fc30Slice = fc90.slice(0, 30);
  const fc60Slice = fc90.slice(0, 60);
  const fcRoas30 = forecastRoas(rows, 30).filter((p) => !p.historical);

  return {
    totalRevenue: Math.round(totalRevenue),
    totalSpend: Math.round(totalSpend),
    avgRoas: Math.round(avgRoas * 100) / 100,
    totalCampaigns: campaignKeys.size,
    revenueTrendPct,
    spendTrendPct,
    roasTrendPct,
    forecast30dRevenue: Math.round(fc30Slice.reduce((s, p) => s + p.value, 0)),
    forecast60dRevenue: Math.round(fc60Slice.reduce((s, p) => s + p.value, 0)),
    forecast90dRevenue: Math.round(fc90.reduce((s, p) => s + p.value, 0)),
    forecast30dRevenueLower: Math.round(fc30Slice.reduce((s, p) => s + p.lower, 0)),
    forecast30dRevenueUpper: Math.round(fc30Slice.reduce((s, p) => s + p.upper, 0)),
    forecast30dRoas: fcRoas30.length
      ? Math.round((fcRoas30.reduce((s, p) => s + p.value, 0) / fcRoas30.length) * 100) / 100
      : 0,
    channels,
    topCampaigns,
    bottomCampaigns,
    campaignTypeBreakdown,
  };
}

function Stat({ label, value, delta }: { label: string; value: string; delta?: number }) {
  return (
    <Card className="bg-gradient-card border-border/60 p-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <div className="text-xl font-bold">{value}</div>
        {typeof delta === "number" && delta !== 0 && (
          <span
            className={`text-[11px] font-medium ${delta > 0 ? "text-success" : "text-destructive"}`}
          >
            {delta > 0 ? "+" : ""}
            {delta.toFixed(1)}%
          </span>
        )}
      </div>
    </Card>
  );
}

function SectionCard({
  icon: Icon,
  title,
  accent,
  children,
}: {
  icon: LucideIcon;
  title: string;
  accent: "primary" | "success" | "warning" | "destructive";
  children: React.ReactNode;
}) {
  const accentBg: Record<string, string> = {
    primary: "bg-primary/15 text-primary",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    destructive: "bg-destructive/15 text-destructive",
  };
  return (
    <Card className="bg-gradient-card border-border/60 p-5">
      <div className="mb-4 flex items-center gap-3">
        <div className={`grid h-9 w-9 place-items-center rounded-lg ${accentBg[accent]}`}>
          <Icon className="h-4 w-4" />
        </div>
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {children}
    </Card>
  );
}

function VerdictBadge({ verdict }: { verdict: "outperforming" | "on_track" | "underperforming" }) {
  const map = {
    outperforming: { cls: "bg-success/15 text-success border-success/30", label: "Outperforming" },
    on_track: { cls: "bg-primary/15 text-primary border-primary/30", label: "On track" },
    underperforming: {
      cls: "bg-destructive/15 text-destructive border-destructive/30",
      label: "Underperforming",
    },
  } as const;
  const v = map[verdict] ?? map.on_track;
  return (
    <Badge variant="outline" className={`text-[10px] ${v.cls}`}>
      {v.label}
    </Badge>
  );
}

function SeverityBadge({ severity }: { severity: "low" | "medium" | "high" }) {
  const map = {
    low: { cls: "bg-muted text-muted-foreground border-border", label: "Low" },
    medium: { cls: "bg-warning/15 text-warning border-warning/30", label: "Medium" },
    high: { cls: "bg-destructive/15 text-destructive border-destructive/30", label: "High" },
  } as const;
  const s = map[severity] ?? map.medium;
  return (
    <Badge variant="outline" className={`text-[10px] ${s.cls}`}>
      {s.label} risk
    </Badge>
  );
}

function EffortBadge({ effort }: { effort: "low" | "medium" | "high" }) {
  const map = {
    low: { cls: "bg-success/15 text-success border-success/30", label: "Low effort" },
    medium: { cls: "bg-warning/15 text-warning border-warning/30", label: "Med effort" },
    high: { cls: "bg-destructive/15 text-destructive border-destructive/30", label: "High effort" },
  } as const;
  const e = map[effort] ?? map.medium;
  return (
    <Badge variant="outline" className={`text-[10px] ${e.cls}`}>
      {e.label}
    </Badge>
  );
}

function PriorityBadge({ priority }: { priority: "high" | "medium" | "low" }) {
  const map = {
    high: {
      cls: "bg-destructive/15 text-destructive border-destructive/30",
      label: "High priority",
    },
    medium: { cls: "bg-warning/15 text-warning border-warning/30", label: "Medium priority" },
    low: { cls: "bg-muted text-muted-foreground border-border", label: "Low priority" },
  } as const;
  const p = map[priority] ?? map.medium;
  return (
    <Badge variant="outline" className={`text-[10px] ${p.cls}`}>
      {p.label}
    </Badge>
  );
}
