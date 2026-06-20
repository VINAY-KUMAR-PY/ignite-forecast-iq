import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
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
import {
  Activity,
  AlertTriangle,
  ArrowRightLeft,
  Brain,
  DollarSign,
  Gauge,
  Lightbulb,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
  decisionSupportApi,
  simulateBudgetsApi,
  type ChannelHealthScore,
  type DecisionSupportResponse,
  type DetectionItem,
  type SimChannelResult,
  type WhatIfScenarioResult,
} from "@/lib/backend-api";
import type { CampaignRow } from "@/lib/types";

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

type PieTooltipPayload = {
  payload?: {
    name: string;
    value: number;
    share: number;
  };
};

type TooltipPayload = {
  dataKey: string;
  name?: string;
  color: string;
  value: number;
};

type CampaignBudgetMove = {
  fromCampaign: string;
  fromChannel: string;
  toCampaign: string;
  toChannel: string;
  shiftBudget: number;
  rationale: string;
};

type OptimizerBrief = {
  channelMove: string;
  campaignMove: string;
  revenueLift: number;
  roasLift: number;
  confidenceScore: number;
  riskLevel: "Low" | "Medium" | "High";
  explanation: string;
};

function SimulatorPage() {
  const { rows } = useData();
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [budgets, setBudgets] = useState<Record<string, number>>({});
  const [apiSims, setApiSims] = useState<SimChannelResult[] | null>(null);
  const [decisionSupport, setDecisionSupport] = useState<DecisionSupportResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [targetRevenueDraft, setTargetRevenueDraft] = useState("");
  const [targetRoasDraft, setTargetRoasDraft] = useState("");
  const [targets, setTargets] = useState<{ targetRevenue?: number; targetRoas?: number }>({});

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

  const totalBudget = (ch: string) =>
    budgets[ch] ?? Math.round((baselines?.[ch]?.dailySpend ?? 0) * horizon);

  const budgetPayload = useMemo(() => {
    if (!baselines) return {};
    return Object.fromEntries(CHANNELS.map((ch) => [ch, totalBudget(ch)]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baselines, horizon, JSON.stringify(budgets)]);

  const baselineSims: SimChannelResult[] = useMemo(() => {
    if (!rows.length || !baselines) return [];
    const dates = [...new Set(rows.map((r) => r.date))].sort();
    const recentDates = new Set(dates.slice(-Math.min(30, dates.length)));
    const recentRows = rows.filter((r) => recentDates.has(r.date));

    return CHANNELS.map((ch) => {
      const channelRows = recentRows.filter((r) => r.channel === ch);
      const activeDays = Math.max(1, new Set(channelRows.map((r) => r.date)).size);
      const baselineDailySpend = channelRows.reduce((sum, row) => sum + row.spend, 0) / activeDays;
      const baselineDailyRevenue =
        channelRows.reduce((sum, row) => sum + row.revenue, 0) / activeDays;
      const baselineTotalSpend = baselineDailySpend * horizon;
      const baselineRevenue = baselineDailyRevenue * horizon;
      const newTotalSpend = totalBudget(ch);
      const spendRatio = baselineTotalSpend > 0 ? newTotalSpend / baselineTotalSpend : 1;
      const projectedRevenue = baselineRevenue * Math.pow(Math.max(0, spendRatio), 0.85);

      return {
        channel: ch,
        horizonDays: horizon,
        baselineDailySpend,
        newDailySpend: newTotalSpend / horizon,
        baselineTotalSpend,
        newTotalSpend,
        baselineRevenue,
        projectedRevenue,
        projectedRevenueLower: projectedRevenue * 0.85,
        projectedRevenueUpper: projectedRevenue * 1.15,
        baselineRoas: baselineTotalSpend > 0 ? baselineRevenue / baselineTotalSpend : 0,
        projectedRoas: newTotalSpend > 0 ? projectedRevenue / newTotalSpend : 0,
        daily: [],
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, horizon, baselines, JSON.stringify(budgets)]);

  useEffect(() => {
    if (!rows.length || !baselines) return;
    let active = true;
    simulateBudgetsApi(rows, horizon, budgetPayload)
      .then((response) => {
        if (!active) return;
        setApiSims(response.channels);
      })
      .catch(() => {
        if (!active) return;
        setApiSims(null);
      });
    return () => {
      active = false;
    };
  }, [rows, horizon, baselines, budgetPayload]);

  useEffect(() => {
    if (!rows.length || !baselines) return;
    let active = true;
    setDecisionError(null);
    decisionSupportApi(rows, horizon, budgetPayload, targets)
      .then((response) => {
        if (!active) return;
        setDecisionSupport(response);
      })
      .catch((error: Error) => {
        if (!active) return;
        setDecisionSupport(null);
        setDecisionError(error.message);
      });
    return () => {
      active = false;
    };
  }, [rows, horizon, baselines, budgetPayload, targets]);

  const sims = apiSims ?? baselineSims;

  if (!rows.length || !baselines) {
    return (
      <>
        <PageHeader title="Budget simulator" />
        <EmptyState />
      </>
    );
  }

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
  const campaignBudgetMove = buildCampaignBudgetMove(rows, totalNewSpend);
  const optimizerBrief = decisionSupport
    ? buildOptimizerBrief(decisionSupport, totalProjRev, projRoas, campaignBudgetMove)
    : null;

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

  function applyTargets() {
    const targetRevenue = Number(targetRevenueDraft);
    const targetRoas = Number(targetRoasDraft);
    setTargets({
      targetRevenue:
        Number.isFinite(targetRevenue) && targetRevenue > 0 ? targetRevenue : undefined,
      targetRoas: Number.isFinite(targetRoas) && targetRoas > 0 ? targetRoas : undefined,
    });
  }

  function applyBudgetScenario(multiplier: number) {
    if (!baselines) return;
    setBudgets(
      Object.fromEntries(
        CHANNELS.map((ch) => [
          ch,
          Math.max(0, Math.round((baselines[ch]?.dailySpend ?? 0) * horizon * multiplier)),
        ]),
      ),
    );
  }

  return (
    <>
      <PageHeader
        title="Budget simulator"
        description="XGBoost-powered live simulation. Move a slider and the backend re-forecasts every channel."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="bg-gradient-card border-border/60 p-6 lg:col-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Channel budgets</h3>
              <p className="text-xs text-muted-foreground">Set spend for the next {horizon} days</p>
            </div>
            <Select
              value={String(horizon)}
              onValueChange={(v) => setHorizon(Number(v) as 30 | 60 | 90)}
            >
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
                      onValueChange={(val) => setBudgets((s) => ({ ...s, [ch]: val[0] }))}
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

          <div className="mt-6 rounded-lg border border-border/40 bg-background/40 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Quick scenarios
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Apply common budget changes across all channels.
                </p>
              </div>
              <Sparkles className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Button
                type="button"
                variant="outline"
                className="h-8 text-xs"
                onClick={() => applyBudgetScenario(0.9)}
              >
                -10%
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-8 text-xs"
                onClick={() => applyBudgetScenario(1.1)}
              >
                +10%
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-8 text-xs"
                onClick={() => applyBudgetScenario(1.2)}
              >
                +20%
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-8 text-xs"
                onClick={() => applyBudgetScenario(1.5)}
              >
                +50%
              </Button>
            </div>
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
                  <p className="text-xs text-muted-foreground">Share of projected revenue</p>
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
                    isAnimationActive={false}
                  >
                    {contributionData.map((d) => (
                      <Cell key={d.name} fill={d.color} stroke="var(--color-background)" />
                    ))}
                  </Pie>
                  <Tooltip
                    content={(props) => {
                      const { active, payload } = props as {
                        active?: boolean;
                        payload?: PieTooltipPayload[];
                      };
                      if (!active || !payload?.length) return null;
                      const d = payload[0].payload;
                      if (!d) return null;
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
                      <span className="h-2 w-2 rounded-full" style={{ background: d.color }} />
                      <span>{d.name}</span>
                    </div>
                    <span className="font-medium tabular-nums">{fmtPct(d.share)}</span>
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
                  <Bar
                    dataKey="Baseline revenue"
                    fill="var(--color-muted)"
                    radius={[6, 6, 0, 0]}
                    isAnimationActive={false}
                  />
                  <Bar
                    dataKey="Projected revenue"
                    fill="var(--color-chart-1)"
                    radius={[6, 6, 0, 0]}
                    isAnimationActive={false}
                  />
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
                  XGBoost model
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
                    isAnimationActive={false}
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
                    isAnimationActive={false}
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
                    isAnimationActive={false}
                    name="Lower 95%"
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}

          <Card data-testid="channel-breakdown" className="bg-gradient-card border-border/60 p-5">
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
                        <td className="px-2 py-2 text-right">{fmtCurrency(p.newTotalSpend)}</td>
                        <td className="px-2 py-2 text-right">{fmtCurrency(p.projectedRevenue)}</td>
                        <td className="px-2 py-2 text-right">{fmtRoas(p.projectedRoas)}</td>
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

      {decisionError && (
        <Card className="mt-6 border-warning/40 bg-warning/5 p-4 text-sm text-warning">
          Decision-support engine unavailable: {decisionError}
        </Card>
      )}

      {decisionSupport && (
        <div data-testid="decision-support" className="mt-6 grid gap-4">
          <Card data-testid="ai-budget-optimizer" className="bg-gradient-card border-border/60 p-5">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" />
                  <h3 className="text-sm font-semibold">AI budget optimizer</h3>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Set target revenue and ROAS, then compare recommended Google, Meta and Microsoft
                  budgets.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-[140px_120px_auto]">
                <Input
                  type="number"
                  min={0}
                  value={targetRevenueDraft}
                  onChange={(event) => setTargetRevenueDraft(event.target.value)}
                  placeholder={`${Math.round(totalProjRev * 1.1)}`}
                  aria-label="Target revenue"
                />
                <Input
                  type="number"
                  min={0}
                  step="0.1"
                  value={targetRoasDraft}
                  onChange={(event) => setTargetRoasDraft(event.target.value)}
                  placeholder={`${Math.max(0, projRoas * 1.05).toFixed(1)}`}
                  aria-label="Target ROAS"
                />
                <Button type="button" variant="hero" onClick={applyTargets}>
                  <Target className="mr-2 h-4 w-4" />
                  Optimize
                </Button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-4">
              <DecisionStat
                label="Recommended budget"
                value={fmtCurrency(decisionSupport.optimizer.recommendedBudget)}
                hint={`current ${fmtCurrency(decisionSupport.optimizer.currentBudget)}`}
              />
              <DecisionStat
                label="Expected revenue"
                value={fmtCurrency(decisionSupport.optimizer.expectedRevenue)}
                hint={formatTargetGap(decisionSupport.optimizer.targetGapRevenue, "revenue")}
              />
              <DecisionStat
                label="Expected ROAS"
                value={fmtRoas(decisionSupport.optimizer.expectedRoas)}
                hint={formatTargetGap(decisionSupport.optimizer.targetGapRoas, "roas")}
              />
              <DecisionStat
                label="Expected profit"
                value={fmtCurrency(decisionSupport.optimizer.expectedProfit)}
                hint="revenue minus media spend"
              />
            </div>

            {optimizerBrief && (
              <div
                data-testid="optimizer-executive-brief"
                className="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-4"
              >
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-primary">
                      Optimizer recommendation
                    </div>
                    <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                      {optimizerBrief.explanation}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge
                      variant="outline"
                      className={optimizerConfidenceBadgeClass(optimizerBrief.confidenceScore)}
                    >
                      {optimizerBrief.confidenceScore}/100 confidence
                    </Badge>
                    <Badge
                      variant="outline"
                      className={optimizerRiskBadgeClass(optimizerBrief.riskLevel)}
                    >
                      {optimizerBrief.riskLevel} risk
                    </Badge>
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <DecisionStat
                    label="Channel shift"
                    value={optimizerBrief.channelMove}
                    hint="exact media move"
                  />
                  <DecisionStat
                    label="Campaign shift"
                    value={optimizerBrief.campaignMove}
                    hint="campaign-level action"
                  />
                  <DecisionStat
                    label="Revenue lift"
                    value={formatMoneyDelta(optimizerBrief.revenueLift)}
                    hint="vs current plan"
                  />
                  <DecisionStat
                    label="ROAS improvement"
                    value={formatRoasDelta(optimizerBrief.roasLift)}
                    hint="expected blended lift"
                  />
                </div>
              </div>
            )}

            <div className="mt-4 rounded-lg border border-border/40 bg-background/40 p-4">
              <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Recommended allocation
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Channel-level action plan for the next {horizon} days.
                  </p>
                </div>
                <div className="text-right text-xs">
                  <div className="font-medium text-success">
                    {formatMoneyDelta(decisionSupport.optimizer.expectedRevenue - totalProjRev)}
                  </div>
                  <div className="text-muted-foreground">
                    Revenue lift,{" "}
                    {formatRoasDelta(decisionSupport.optimizer.expectedRoas - projRoas)} ROAS
                  </div>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {decisionSupport.optimizer.recommendations.map((recommendation) => (
                  <div
                    key={recommendation.channel}
                    className="rounded-md border border-border/40 bg-background/50 p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium">{recommendation.channel}</div>
                      <span
                        className={`text-xs font-semibold ${deltaClass(recommendation.deltaBudget)}`}
                      >
                        {formatMoneyDelta(recommendation.deltaBudget)}
                      </span>
                    </div>
                    <div className="mt-2 text-lg font-semibold">
                      {fmtCurrency(recommendation.recommendedBudget)}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Expected ROAS {fmtRoas(recommendation.expectedRoas)}
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">{recommendation.rationale}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 text-left">Channel</th>
                    <th className="px-2 py-2 text-right">Current</th>
                    <th className="px-2 py-2 text-right">Recommended</th>
                    <th className="px-2 py-2 text-right">Delta</th>
                    <th className="px-2 py-2 text-right">Expected ROAS</th>
                    <th className="px-2 py-2 text-left">Rationale</th>
                  </tr>
                </thead>
                <tbody>
                  {decisionSupport.optimizer.recommendations.map((recommendation) => (
                    <tr key={recommendation.channel} className="border-t border-border/40">
                      <td className="px-2 py-2 font-medium">{recommendation.channel}</td>
                      <td className="px-2 py-2 text-right text-muted-foreground">
                        {fmtCurrency(recommendation.currentBudget)}
                      </td>
                      <td className="px-2 py-2 text-right">
                        {fmtCurrency(recommendation.recommendedBudget)}
                      </td>
                      <td
                        className={`px-2 py-2 text-right font-medium ${deltaClass(
                          recommendation.deltaBudget,
                        )}`}
                      >
                        {formatMoneyDelta(recommendation.deltaBudget)}
                      </td>
                      <td className="px-2 py-2 text-right">
                        {fmtRoas(recommendation.expectedRoas)}
                      </td>
                      <td className="max-w-[260px] px-2 py-2 text-xs text-muted-foreground">
                        {recommendation.rationale}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card data-testid="what-if-engine" className="bg-gradient-card border-border/60 p-5">
              <div className="mb-4 flex items-center gap-2">
                <ArrowRightLeft className="h-4 w-4 text-primary" />
                <h3 className="text-sm font-semibold">What-if scenario engine</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="px-2 py-2 text-left">Scenario</th>
                      <th className="px-2 py-2 text-right">Revenue</th>
                      <th className="px-2 py-2 text-right">ROAS</th>
                      <th className="px-2 py-2 text-right">Profit</th>
                      <th className="px-2 py-2 text-right">Revenue impact</th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisionSupport.scenarios.slice(0, 7).map((scenario) => (
                      <ScenarioRow key={scenario.name} scenario={scenario} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card data-testid="channel-health" className="bg-gradient-card border-border/60 p-5">
              <div className="mb-4 flex items-center gap-2">
                <Gauge className="h-4 w-4 text-primary" />
                <h3 className="text-sm font-semibold">Channel health score</h3>
              </div>
              <p className="mb-4 text-xs leading-relaxed text-muted-foreground">
                Formula: projected ROAS plus revenue trend plus budget-share fit, minus efficiency
                risk penalties. 80+ is healthy, 60-79 needs watch, below 60 is critical.
              </p>
              <div className="space-y-4">
                {decisionSupport.channelHealth.map((item) => (
                  <HealthRow key={item.channel} item={item} />
                ))}
              </div>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <DetectionPanel
              title="Risk detection engine"
              icon={AlertTriangle}
              items={decisionSupport.risks}
              testId="risk-detection"
            />
            <DetectionPanel
              title="Opportunity detection engine"
              icon={Lightbulb}
              items={decisionSupport.opportunities}
              testId="opportunity-detection"
            />
          </div>
        </div>
      )}
    </>
  );
}

function DecisionStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border/40 bg-background/40 p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

function buildCampaignBudgetMove(rows: CampaignRow[], totalBudget: number) {
  const campaignMap = new Map<
    string,
    { channel: string; campaign: string; spend: number; revenue: number }
  >();
  for (const row of rows) {
    const key = `${row.channel}|${row.campaign_name}`;
    const item = campaignMap.get(key) ?? {
      channel: row.channel,
      campaign: row.campaign_name,
      spend: 0,
      revenue: 0,
    };
    item.spend += row.spend;
    item.revenue += row.revenue;
    campaignMap.set(key, item);
  }

  const campaigns = [...campaignMap.values()]
    .filter((item) => item.spend > 0)
    .map((item) => ({ ...item, roas: item.revenue / item.spend }));
  if (campaigns.length < 2) return null;

  const totalSpend = campaigns.reduce((sum, item) => sum + item.spend, 0);
  const averageRoas =
    totalSpend > 0 ? campaigns.reduce((sum, item) => sum + item.revenue, 0) / totalSpend : 0;
  const best = [...campaigns].sort((a, b) => b.roas - a.roas || b.revenue - a.revenue)[0];
  const weakest =
    [...campaigns]
      .filter((item) => item.campaign !== best.campaign || item.channel !== best.channel)
      .filter((item) => item.spend >= totalSpend * 0.015 || item.roas < averageRoas)
      .sort((a, b) => a.roas - b.roas || b.spend - a.spend)[0] ??
    [...campaigns]
      .filter((item) => item.campaign !== best.campaign || item.channel !== best.channel)
      .sort((a, b) => a.roas - b.roas)[0];

  if (!best || !weakest) return null;
  const shiftBudget = Math.max(
    100,
    Math.round(Math.min(weakest.spend * 0.08, Math.max(100, totalBudget * 0.08))),
  );

  return {
    fromCampaign: weakest.campaign,
    fromChannel: weakest.channel,
    toCampaign: best.campaign,
    toChannel: best.channel,
    shiftBudget,
    rationale: `${best.campaign} is outperforming at ${fmtRoas(best.roas)} while ${weakest.campaign} trails at ${fmtRoas(weakest.roas)}.`,
  } satisfies CampaignBudgetMove;
}

function buildOptimizerBrief(
  decisionSupport: DecisionSupportResponse,
  currentRevenue: number,
  currentRoas: number,
  campaignMove: CampaignBudgetMove | null,
): OptimizerBrief {
  const recommendations = decisionSupport.optimizer.recommendations;
  const increase = [...recommendations].sort((a, b) => b.deltaBudget - a.deltaBudget)[0];
  const decrease = [...recommendations].sort((a, b) => a.deltaBudget - b.deltaBudget)[0];
  const hasChannelShift =
    increase && decrease && increase.deltaBudget > 0 && decrease.deltaBudget < 0;
  const channelShift = hasChannelShift
    ? Math.min(increase.deltaBudget, Math.abs(decrease.deltaBudget))
    : Math.max(0, increase?.deltaBudget ?? 0);
  const channelMove =
    hasChannelShift && channelShift > 0
      ? `${fmtCurrency(channelShift)} ${decrease.channel} -> ${increase.channel}`
      : increase && channelShift > 0
        ? `Add ${fmtCurrency(channelShift)} to ${increase.channel}`
        : "Hold current channel mix";
  const campaignMoveText = campaignMove
    ? `${fmtCurrency(campaignMove.shiftBudget)} ${campaignMove.fromCampaign} -> ${campaignMove.toCampaign}`
    : "No campaign cut required";
  const revenueLift = decisionSupport.optimizer.expectedRevenue - currentRevenue;
  const roasLift = decisionSupport.optimizer.expectedRoas - currentRoas;
  const highRisks = decisionSupport.risks.filter((item) => item.severity === "high").length;
  const mediumRisks = decisionSupport.risks.filter((item) => item.severity === "medium").length;
  const averageHealth = decisionSupport.channelHealth.length
    ? decisionSupport.channelHealth.reduce((sum, item) => sum + item.score, 0) /
      decisionSupport.channelHealth.length
    : 74;
  const confidenceScore = Math.round(
    clampNumber(
      averageHealth - highRisks * 8 - mediumRisks * 4 + Math.min(8, Math.max(0, roasLift) * 12),
      55,
      96,
    ),
  );
  const riskLevel: OptimizerBrief["riskLevel"] =
    highRisks > 0 ? "High" : mediumRisks > 0 || confidenceScore < 72 ? "Medium" : "Low";
  const explanation =
    hasChannelShift && campaignMove
      ? `Recycle inefficient spend from ${decrease.channel} and ${campaignMove.fromCampaign} into the highest-return areas. The plan protects ROAS while still funding growth. ${campaignMove.rationale}`
      : increase
        ? `The safest next move is to fund ${increase.channel} while keeping the rest of the plan close to baseline. This keeps the simulator in a controlled growth posture.`
        : "The current plan is already balanced; keep budgets steady and monitor marginal ROAS before scaling.";

  return {
    channelMove,
    campaignMove: campaignMoveText,
    revenueLift,
    roasLift,
    confidenceScore,
    riskLevel,
    explanation,
  };
}

function ScenarioRow({ scenario }: { scenario: WhatIfScenarioResult }) {
  return (
    <tr className="border-t border-border/40">
      <td className="px-2 py-2 font-medium">{scenario.name}</td>
      <td className="px-2 py-2 text-right">{fmtCurrency(scenario.projectedRevenue)}</td>
      <td className="px-2 py-2 text-right">{fmtRoas(scenario.projectedRoas)}</td>
      <td className="px-2 py-2 text-right">{fmtCurrency(scenario.projectedProfit)}</td>
      <td className={`px-2 py-2 text-right font-medium ${deltaClass(scenario.revenueDeltaPct)}`}>
        {formatPctDelta(scenario.revenueDeltaPct)}
      </td>
    </tr>
  );
}

function HealthRow({ item }: { item: ChannelHealthScore }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">{item.channel}</div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            Revenue share {item.revenueSharePct.toFixed(1)}% · Spend share{" "}
            {item.spendSharePct.toFixed(1)}%
          </div>
        </div>
        <Badge variant="outline" className={healthBadgeClass(item.status)}>
          {item.score.toFixed(0)}/100 · {item.status}
        </Badge>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary"
          style={{ width: `${Math.min(100, Math.max(0, item.score))}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.drivers.map((driver) => (
          <span
            key={driver}
            className="rounded-full border border-border/40 bg-background/40 px-2 py-0.5 text-[10px] text-muted-foreground"
          >
            {driver}
          </span>
        ))}
      </div>
    </div>
  );
}

function DetectionPanel({
  title,
  icon: Icon,
  items,
  testId,
}: {
  title: string;
  icon: typeof AlertTriangle;
  items: DetectionItem[];
  testId: string;
}) {
  return (
    <Card data-testid={testId} className="bg-gradient-card border-border/60 p-5">
      <div className="mb-4 flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="space-y-3">
        {items.map((item, index) => (
          <div
            key={`${item.type}-${item.channel ?? index}`}
            className="rounded-lg border border-border/40 bg-background/40 p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-medium">
                {item.channel ?? item.type.replaceAll("_", " ")}
              </div>
              <Badge variant="outline" className={severityBadgeClass(item.severity)}>
                {item.severity} · {item.score.toFixed(0)}
              </Badge>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{item.message}</p>
            <p className="mt-2 text-xs">
              <span className="font-medium text-foreground">Action: </span>
              <span className="text-muted-foreground">{item.recommendation}</span>
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function formatMoneyDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${fmtCurrency(value)}`;
}

function formatPctDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatRoasDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}x`;
}

function formatTargetGap(value: number, type: "revenue" | "roas") {
  if (!value) return "target met or not set";
  if (value <= 0) return "target met";
  return type === "revenue" ? `${fmtCurrency(value)} gap` : `${value.toFixed(2)}x gap`;
}

function deltaClass(value: number) {
  if (value > 0) return "text-success";
  if (value < 0) return "text-destructive";
  return "text-muted-foreground";
}

function severityBadgeClass(severity: DetectionItem["severity"]) {
  if (severity === "high") return "border-destructive/30 bg-destructive/15 text-destructive";
  if (severity === "medium") return "border-warning/30 bg-warning/15 text-warning";
  return "border-border bg-muted text-muted-foreground";
}

function healthBadgeClass(status: ChannelHealthScore["status"]) {
  if (status === "healthy") return "border-success/30 bg-success/15 text-success";
  if (status === "watch") return "border-warning/30 bg-warning/15 text-warning";
  return "border-destructive/30 bg-destructive/15 text-destructive";
}

function optimizerConfidenceBadgeClass(score: number) {
  if (score >= 85) return "border-success/30 bg-success/15 text-success";
  if (score >= 70) return "border-primary/30 bg-primary/15 text-primary";
  return "border-warning/30 bg-warning/15 text-warning";
}

function optimizerRiskBadgeClass(level: OptimizerBrief["riskLevel"]) {
  if (level === "High") return "border-destructive/30 bg-destructive/15 text-destructive";
  if (level === "Medium") return "border-warning/30 bg-warning/15 text-warning";
  return "border-success/30 bg-success/15 text-success";
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

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
      <div className="font-medium">
        {label && /\d{4}-\d{2}-\d{2}/.test(label) ? fmtDate(label) : label}
      </div>
      {payload.map((p) => (
        <div key={p.dataKey} className="mt-1 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name ?? p.dataKey}:</span>
          <span className="font-medium">{formatter ? formatter(p.value) : p.value}</span>
        </div>
      ))}
    </div>
  );
}
