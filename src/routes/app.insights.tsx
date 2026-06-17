import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { AlertTriangle, ArrowUpRight, Brain, Lightbulb, Sparkles, Target, TrendingUp, Wallet } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useData } from "@/lib/data-store";
import { aggregateDaily, forecastRevenue } from "@/lib/forecasting";
import { generateInsights } from "@/lib/ai-insights.functions";
import { fmtCurrency, fmtRoas } from "@/lib/format";

export const Route = createFileRoute("/app/insights")({
  head: () => ({ meta: [{ title: "AI Insights · ForecastIQ" }] }),
  component: InsightsPage,
});

interface Insights {
  executiveSummary: string;
  revenueDrivers: string[];
  topChannels: string[];
  underperformingCampaigns: string[];
  risks: string[];
  opportunities: string[];
  budgetRecommendations: string[];
  growthRecommendations: string[];
}

function InsightsPage() {
  const { rows } = useData();
  const [insights, setInsights] = useState<Insights | null>(null);
  const [loading, setLoading] = useState(false);
  const gen = useServerFn(generateInsights);

  const summary = useMemo(() => {
    if (!rows.length) return null;
    const totalRevenue = rows.reduce((s, r) => s + r.revenue, 0);
    const totalSpend = rows.reduce((s, r) => s + r.spend, 0);
    const avgRoas = totalSpend > 0 ? totalRevenue / totalSpend : 0;
    const campaigns = new Set(rows.map((r) => `${r.channel}|${r.campaign_name}`));
    const chMap = new Map<string, { revenue: number; spend: number }>();
    for (const r of rows) {
      const c = chMap.get(r.channel) ?? { revenue: 0, spend: 0 };
      c.revenue += r.revenue;
      c.spend += r.spend;
      chMap.set(r.channel, c);
    }
    const channels = [...chMap.entries()].map(([name, v]) => ({
      name,
      revenue: Math.round(v.revenue),
      spend: Math.round(v.spend),
      roas: v.spend > 0 ? Math.round((v.revenue / v.spend) * 100) / 100 : 0,
    }));

    const cMap = new Map<string, { revenue: number; spend: number; channel: string }>();
    for (const r of rows) {
      const k = `${r.channel}|${r.campaign_name}`;
      const c = cMap.get(k) ?? { revenue: 0, spend: 0, channel: r.channel };
      c.revenue += r.revenue;
      c.spend += r.spend;
      cMap.set(k, c);
    }
    const campaignsArr = [...cMap.entries()].map(([k, v]) => ({
      name: k.split("|")[1],
      channel: v.channel,
      revenue: Math.round(v.revenue),
      spend: Math.round(v.spend),
      roas: v.spend > 0 ? Math.round((v.revenue / v.spend) * 100) / 100 : 0,
    }));
    const topCampaigns = [...campaignsArr].sort((a, b) => b.revenue - a.revenue).slice(0, 5);
    const bottomCampaigns = [...campaignsArr].filter((c) => c.spend > 100).sort((a, b) => a.roas - b.roas).slice(0, 5);

    const daily = aggregateDaily(rows);
    const last30 = daily.slice(-30).reduce((s, d) => s + d.revenue, 0);
    const prev30 = daily.slice(-60, -30).reduce((s, d) => s + d.revenue, 0) || 1;
    const revenueTrendPct = Math.round(((last30 - prev30) / prev30) * 1000) / 10;
    const fc30 = forecastRevenue(rows, 30).filter((p) => !p.historical).reduce((s, p) => s + p.value, 0);

    return {
      totalRevenue: Math.round(totalRevenue),
      totalSpend: Math.round(totalSpend),
      avgRoas: Math.round(avgRoas * 100) / 100,
      totalCampaigns: campaigns.size,
      channels,
      topCampaigns,
      bottomCampaigns,
      forecast30dRevenue: Math.round(fc30),
      revenueTrendPct,
    };
  }, [rows]);

  if (!rows.length || !summary) return (<><PageHeader title="AI insights" /><EmptyState /></>);

  async function run() {
    setLoading(true);
    try {
      const res = await gen({ data: { summary: summary! } });
      setInsights(res as Insights);
      toast.success("Executive briefing generated");
    } catch (e: any) {
      toast.error(e?.message ?? "Failed to generate insights");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="AI executive insights"
        description="Generate a board-ready briefing across drivers, risks and budget allocation."
        actions={
          <Button variant="hero" onClick={run} disabled={loading}>
            <Sparkles className="mr-2 h-4 w-4" />
            {loading ? "Analyzing…" : insights ? "Regenerate" : "Generate insights"}
          </Button>
        }
      />

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <Stat label="Revenue (all time)" value={fmtCurrency(summary.totalRevenue)} />
        <Stat label="Spend (all time)" value={fmtCurrency(summary.totalSpend)} />
        <Stat label="Avg ROAS" value={fmtRoas(summary.avgRoas)} />
        <Stat label="30d forecast" value={fmtCurrency(summary.forecast30dRevenue)} />
      </div>

      {!insights && !loading && (
        <Card className="bg-gradient-card border-border/60 p-10 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-gradient-brand shadow-glow">
            <Brain className="h-5 w-5 text-primary-foreground" />
          </div>
          <h3 className="mt-4 text-lg font-semibold">Ready when you are</h3>
          <p className="mt-2 text-sm text-muted-foreground">Click <em>Generate insights</em> to produce an AI-written executive briefing.</p>
        </Card>
      )}

      {loading && (
        <Card className="bg-gradient-card border-border/60 p-10 text-center">
          <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="mt-4 text-sm text-muted-foreground">Analyzing {rows.length.toLocaleString()} rows across {summary.channels.length} channels…</p>
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

          <div className="grid gap-6 lg:grid-cols-2">
            <Section icon={TrendingUp} title="Revenue drivers" items={insights.revenueDrivers} accent="success" />
            <Section icon={Target} title="Top performing channels" items={insights.topChannels} accent="primary" />
            <Section icon={AlertTriangle} title="Underperforming campaigns" items={insights.underperformingCampaigns} accent="warning" />
            <Section icon={AlertTriangle} title="Risks" items={insights.risks} accent="destructive" />
            <Section icon={Lightbulb} title="Opportunities" items={insights.opportunities} accent="primary" />
            <Section icon={Wallet} title="Budget recommendations" items={insights.budgetRecommendations} accent="success" />
            <Section icon={ArrowUpRight} title="Growth recommendations" items={insights.growthRecommendations} accent="primary" className="lg:col-span-2" />
          </div>
        </div>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card className="bg-gradient-card border-border/60 p-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-bold">{value}</div>
    </Card>
  );
}

function Section({
  icon: Icon,
  title,
  items,
  accent,
  className,
}: {
  icon: any;
  title: string;
  items: string[];
  accent: "primary" | "success" | "warning" | "destructive";
  className?: string;
}) {
  const accentBg: Record<string, string> = {
    primary: "bg-primary/15 text-primary",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    destructive: "bg-destructive/15 text-destructive",
  };
  return (
    <Card className={`bg-gradient-card border-border/60 p-5 ${className ?? ""}`}>
      <div className="flex items-center gap-3">
        <div className={`grid h-9 w-9 place-items-center rounded-lg ${accentBg[accent]}`}>
          <Icon className="h-4 w-4" />
        </div>
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <ul className="mt-4 space-y-2 text-sm">
        {items?.map((it, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/40" />
            <span className="text-muted-foreground">{it}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
