import { createFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";
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
import { Activity, DollarSign, Target, TrendingUp } from "lucide-react";
import { useData } from "@/lib/data-store";
import { aggregateDaily } from "@/lib/forecasting";
import { fmtCompact, fmtCurrency, fmtDate, fmtRoas } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";

export const Route = createFileRoute("/app/")({
  head: () => ({ meta: [{ title: "Dashboard · ForecastIQ" }] }),
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
    const revPrev = sum(prev30, "revenue") || 1;
    const spendPrev = sum(prev30, "spend") || 1;
    const revDelta = ((sum(last30, "revenue") - revPrev) / revPrev) * 100;
    const spendDelta = ((sum(last30, "spend") - spendPrev) / spendPrev) * 100;
    const lastRoas = sum(last30, "spend") > 0 ? sum(last30, "revenue") / sum(last30, "spend") : 0;
    const prevRoas = sum(prev30, "spend") > 0 ? sum(prev30, "revenue") / sum(prev30, "spend") : 0;
    const roasDelta = prevRoas > 0 ? ((lastRoas - prevRoas) / prevRoas) * 100 : 0;

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
    };
  }, [rows]);

  if (!stats)
    return (
      <>
        <PageHeader title="Dashboard" />
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
        title="Marketing performance"
        description="Live snapshot of revenue, spend, ROAS and channel performance."
      />

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

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <ChartCard title="Revenue trend" subtitle="Daily revenue over time">
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

        <ChartCard title="Spend trend" subtitle="Daily media spend">
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

        <ChartCard title="ROAS trend" subtitle="Blended ROAS by day">
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

        <ChartCard title="Channel performance" subtitle="Revenue vs spend by channel">
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

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        {stats.channels.map((c, i) => (
          <Card key={c.name} className="bg-gradient-card border-border/60 p-5">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">{c.name}</div>
              <div
                className="h-2 w-2 rounded-full"
                style={{ background: COLORS[i % COLORS.length] }}
              />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
              <div>
                <div className="text-muted-foreground">Revenue</div>
                <div className="mt-1 text-sm font-semibold">{fmtCompact(c.revenue)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Spend</div>
                <div className="mt-1 text-sm font-semibold">{fmtCompact(c.spend)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">ROAS</div>
                <div className="mt-1 text-sm font-semibold">{fmtRoas(c.roas)}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="bg-gradient-card border-border/60 p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {children}
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
