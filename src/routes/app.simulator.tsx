import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, Brain, DollarSign, Target, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useData } from "@/lib/data-store";
import { fmtCompact, fmtCurrency, fmtDate, fmtPct, fmtRoas } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";
import { simulateChannelForecast, type SimChannelResult } from "@/lib/forecasting";

export const Route = createFileRoute("/app/simulator")({
  head: () => ({ meta: [{ title: "Budget simulator · ForecastIQ" }] }),
  component: SimulatorPage,
});

const CHANNELS = ["Google Ads", "Meta Ads", "Microsoft Ads"] as const;
const CHANNEL_COLORS: Record<string, string> = {
  "Google Ads": "var(--color-chart-1)",
  "Meta Ads": "var(--color-chart-2)",
  "Microsoft Ads": "var(--color-chart-3)",
};

function SimulatorPage() {
  const { rows } = useData();
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [budgets, setBudgets] = useState<Record<string, number>>({});

  // Baseline daily spend per channel (recent 30 days)
  const baselines = useMemo(() => {
    if (!rows.length) return null;
    const dates = [...new Set(rows.map((r) => r.date))].sort();
    const lastN = new Set(dates.slice(-30));
    const recent = rows.filter((r) => lastN.has(r.date));
    const out: Record<string, { dailySpend: number }> = {};
    for (const ch of CHANNELS) {
      const chRows = recent.filter((r) => r.channel === ch);
      const spend = chRows.reduce((s, r) => s + r.spend, 0);
      out[ch] = { dailySpend: spend / Math.max(1, [...new Set(chRows.map((r) => r.date))].length) };
    }
    return out;
  }, [rows]);

  if (!rows.length || !baselines) {
    return (
      <>
        <PageHeader title="Budget simulator" />
        <EmptyState />
      </>
    );
  }

  const totalBudget = (ch: string) =>
    budgets[ch] ?? Math.round((baselines[ch]?.dailySpend ?? 0) * horizon);

  // Run GBRT forecast per channel with the chosen daily spend
  const sims: SimChannelResult[] = useMemo(() => {
    return CHANNELS.map((ch) => {
      const total = totalBudget(ch);
      const newDaily = total / horizon;
      return simulateChannelForecast(rows, ch, newDaily, horizon);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, horizon, JSON.stringify(budgets)]);

  const totalNewSpend = sims.reduce((s, p) => s + p.newTotalSpend, 0);
  const totalBaseSpend = sims.reduce((s, p) => s + p.baselineTotalSpend, 0);
  const totalProjRev = sims.reduce((s, p) => s + p.projectedRevenue, 0);
  const totalLowerRev = sims.reduce((s, p) => s + p.projectedRevenueLower, 0);
  const totalUpperRev = sims.reduce((s, p) => s + p.projectedRevenueUpper, 0);
  const totalBaseRev = sims.reduce((s, p) => s + p.baselineRevenue, 0);
  const projRoas = totalNewSpend > 0 ? totalProjRev / totalNewSpend : 0;
  const baseRoas = totalBaseSpend > 0 ? totalBaseRev / totalBaseSpend : 0;
  const revChangePct = totalBaseRev > 0 ? ((totalProjRev - totalBaseRev) / totalBaseRev) * 100 : 0;
  const roasChangePct = baseRoas > 0 ? ((projRoas - baseRoas) / baseRoas) * 100 : 0;

  const chartData = sims.map((p) => ({
    name: p.channel,
    "Baseline revenue": Math.round(p.baselineRevenue),
    "Projected revenue": Math.round(p.projectedRevenue),
  }));

  const contributionData = sims.map((p) => ({
    name: p.channel,
    value: Math.max(0, Math.round(p.projectedRevenue)),
    color: CHANNEL_COLORS[p.channel],
    share: totalProjRev > 0 ? p.projectedRevenue / totalProjRev : 0,
  }));

  // Daily projected trend (sum across channels)
  const dailyTrend = (() => {
    const map = new Map<string, { date: string; revenue: number; lower: number; upper: number }>();
    for (const s of sims) {
      for (const d of s.daily) {
        const cur = map.get(d.date) ?? { date: d.date, revenue: 0, lower: 0, upper: 0 };
        cur.revenue += d.value;
        cur.lower += d.lower;
        cur.upper += d.upper;
        map.set(d.date, cur);
      }
    }
    return [...map.values()].sort((a, b) => (a.date < b.date ? -1 : 1));
  })();

  return (
    <>
      <PageHeader
        title="Budget simulator"
        description="GBRT-powered live simulation. Move a slider — the model re-forecasts every channel."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="bg-gradient-card border-border/60 p-6 lg:col-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Channel budgets</h3>
              <p className="text-xs text-muted-foreground">
                Set spend for the next {horizon} days
              </p>
            </div>
            <Select value={String(horizon)} onValueChange={(v) => setHorizon(Number(v) as 30 | 60 | 90)}>
              <SelectTrigger className="h-8 w-[120px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30 days</SelectItem>
                <SelectItem value="60">60 days</SelectItem>
                <SelectItem value="90">90 days</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="mt-6 space-y-6">
            {CHANNELS.map((ch) => {
              const b = baselines[ch];
              const baseTotal = Math.max(1, Math.round(b.dailySpend * horizon));
              const max = Math.round(baseTotal * 3);
              const v = totalBudget(ch);
              const sim = sims.find((s) => s.channel === ch);
              const delta = baseTotal > 0 ? ((v - baseTotal) / baseTotal) * 100 : 0;
              return (
                <div key={ch}>
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ background: CHANNEL_COLORS[ch] }}
                      />
                      <Label className="font-medium">{ch}</Label>
                    </div>
                    <span
                      className={`text-xs font-medium ${
                        delta > 0
                          ? "text-emerald-500"
                          : delta < 0
                            ? "text-rose-500"
                            : "text-muted-foreground"
                      }`}
                    >
                      {delta >= 0 ? "+" : ""}
                      {delta.toFixed(0)}% vs baseline
                    </span>
                  </div>
                  <div className="mt-3 flex items-center gap-3">
                    <Slider
                      value={[v]}
                      min={0}
                      max={max}
                      step={Math.max(100, Math.round(max / 200))}
                      onValueChange={(val) =>
                        setBudgets((s) => ({ ...s, [ch]: val[0] }))
                      }
                      className="flex-1"
                    />
                    <Input
                      type="number"
                      value={v}
                      onChange={(e) =>
                        setBudgets((s) => ({
                          ...s,
                          [ch]: Math.max(0, Number(e.target.value)),
                        }))
                      }
                      className="w-28"
                    />
                  </div>
                  {sim && (
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                      <span>
                        Proj. rev:{" "}
                        <span className="font-medium text-foreground">
                          {fmtCurrency(sim.projectedRevenue)}
                        </span>
                      </span>
                      <span>
                        ROAS:{" "}
                        <span className="font-medium text-foreground">
                          {fmtRoas(sim.projectedRoas)}
                        </span>
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <button
            type="button"
            onClick={() => setBudgets({})}
            className="mt-6 w-full rounded-md border border-border/60 bg-background/40 px-3 py-2 text-xs font-medium text-muted-foreground transition hover:bg-background/80 hover:text-foreground"
          >
            Reset to baseline
          </button>
        </Card>

        <div className="space-y-4 lg:col-span-3">
          <div className="grid gap-4 sm:grid-cols-2">
            <KpiCard
              label={`Projected revenue (${horizon}d)`}
              value={fmtCurrency(totalProjRev)}
              delta={revChangePct}
              icon={DollarSign}
              hint={`${fmtCurrency(totalLowerRev)} – ${fmtCurrency(totalUpperRev)} · 95% CI`}
            />
            <KpiCard
              label="Projected blended ROAS"
              value={fmtRoas(projRoas)}
              delta={roasChangePct}
              icon={Target}
              hint={`baseline ${fmtRoas(baseRoas)}`}
            />
            <KpiCard
              label="Total spend"
              value={fmtCurrency(totalNewSpend)}
              icon={Activity}
              hint={`baseline ${fmtCurrency(totalBaseSpend)}`}
            />
            <KpiCard
              label="Revenue lift"
              value={`${revChangePct >= 0 ? "+" : ""}${fmtPct(revChangePct / 100)}`}
              icon={TrendingUp}
              hint={fmtCurrency(totalProjRev - totalBaseRev)}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-5">
            <Card className="bg-gradient-card border-border/60 p-5 lg:col-span-3">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold">Channel contribution</h3>
                  <p className="text-xs text-muted-foreground">
                    Share of projected revenue
                  </p>
                </div>
                <Brain className="h-4 w-4 text-muted-foreground" />
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={contributionData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={2}
                  >
                    {contributionData.map((d) => (
                      <Cell key={d.name} fill={d.color} stroke="var(--color-background)" />
                    ))}
                  </Pie>
                  <Tooltip
                    content={({ active, payload }: any) => {
                      if (!active || !payload?.length) return null;
                      const d = payload[0].payload;
                      return (
                        <div className="rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
                          <div className="font-medium">{d.name}</div>
                          <div className="mt-1 text-muted-foreground">
                            {fmtCurrency(d.value)} · {fmtPct(d.share)}
                          </div>
                        </div>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-2 space-y-1.5">
                {contributionData.map((d) => (
                  <div key={d.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ background: d.color }}
                      />
                      <span>{d.name}</span>
                    </div>
                    <span className="font-medium tabular-nums">
                      {fmtPct(d.share)}
                    </span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="bg-gradient-card border-border/60 p-5 lg:col-span-2">
              <h3 className="mb-3 text-sm font-semibold">Baseline vs projected</h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={chartData} margin={{ left: -10, right: 8, top: 8 }}>
                  <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="name"
                    stroke="var(--color-muted-foreground)"
                    fontSize={10}
                    tickFormatter={(v: string) => v.replace(" Ads", "")}
                  />
                  <YAxis
                    stroke="var(--color-muted-foreground)"
                    fontSize={11}
                    tickFormatter={(v) => fmtCompact(v as number)}
                  />
                  <Tooltip content={<TT formatter={fmtCurrency} />} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="Baseline revenue" fill="var(--color-muted)" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="Projected revenue" fill="var(--color-chart-1)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          {dailyTrend.length > 0 && (
            <Card className="bg-gradient-card border-border/60 p-5">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold">Forecast trajectory</h3>
                  <p className="text-xs text-muted-foreground">
                    Daily projected revenue across all channels
                  </p>
                </div>
                <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  GBRT model
                </span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={dailyTrend} margin={{ left: -10, right: 8, top: 8 }}>
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
                  <Line
                    type="monotone"
                    dataKey="revenue"
                    stroke="var(--color-chart-1)"
                    strokeWidth={2}
                    dot={false}
                    name="Expected"
                  />
                  <Line
                    type="monotone"
                    dataKey="upper"
                    stroke="var(--color-chart-1)"
                    strokeWidth={1}
                    strokeDasharray="2 3"
                    strokeOpacity={0.5}
                    dot={false}
                    name="Upper 95%"
                  />
                  <Line
                    type="monotone"
                    dataKey="lower"
                    stroke="var(--color-chart-1)"
                    strokeWidth={1}
                    strokeDasharray="2 3"
                    strokeOpacity={0.5}
                    dot={false}
                    name="Lower 95%"
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          <Card className="bg-gradient-card border-border/60 p-5">
            <h3 className="mb-3 text-sm font-semibold">Channel breakdown</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 text-left">Channel</th>
                    <th className="px-2 py-2 text-right">Baseline spend</th>
                    <th className="px-2 py-2 text-right">New spend</th>
                    <th className="px-2 py-2 text-right">Proj. revenue</th>
                    <th className="px-2 py-2 text-right">Proj. ROAS</th>
                    <th className="px-2 py-2 text-right">Contribution</th>
                  </tr>
                </thead>
                <tbody>
                  {sims.map((p) => {
                    const share = totalProjRev > 0 ? p.projectedRevenue / totalProjRev : 0;
                    return (
                      <tr key={p.channel} className="border-t border-border/40">
                        <td className="px-2 py-2 font-medium">
                          <span className="flex items-center gap-2">
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ background: CHANNEL_COLORS[p.channel] }}
                            />
                            {p.channel}
                          </span>
                        </td>
                        <td className="px-2 py-2 text-right text-muted-foreground">
                          {fmtCurrency(p.baselineTotalSpend)}
                        </td>
                        <td className="px-2 py-2 text-right">
                          {fmtCurrency(p.newTotalSpend)}
                        </td>
                        <td className="px-2 py-2 text-right">
                          {fmtCurrency(p.projectedRevenue)}
                        </td>
                        <td className="px-2 py-2 text-right">
                          {fmtRoas(p.projectedRoas)}
                        </td>
                        <td className="px-2 py-2 text-right">{fmtPct(share)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function TT({ active, payload, label, formatter }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <div className="font-medium">{label && /\d{4}-\d{2}-\d{2}/.test(label) ? fmtDate(label) : label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="mt-1 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name ?? p.dataKey}:</span>
          <span className="font-medium">{formatter ? formatter(p.value) : p.value}</span>
        </div>
      ))}
    </div>
  );
}
