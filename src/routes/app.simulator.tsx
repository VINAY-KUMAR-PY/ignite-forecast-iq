import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Sparkles } from "lucide-react";
import { BudgetSliders, type BudgetSliderChannel } from "@/components/simulator/BudgetSliders";
import { SimulatorResultsPanel } from "@/components/simulator/ChannelResultCard";
import { DecisionSupportPanel } from "@/components/simulator/DecisionSupportPanel";
import { SpendCurveChart } from "@/components/simulator/SpendCurveChart";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  decisionSupportApi,
  fetchSpendCurveApi,
  simulateBudgetsApi,
  type DecisionSupportResponse,
  type SimChannelResult,
  type SpendCurveResponse,
  type WhatIfScenarioInput,
} from "@/lib/backend-api";
import { useData } from "@/lib/data-store";
import { fmtCurrency, fmtRoas } from "@/lib/format";

export const Route = createFileRoute("/app/simulator")({
  head: () => ({ meta: [{ title: "Budget simulator - ForecastIQ" }] }),
  component: SimulatorPage,
});

const CHANNELS = ["Google Ads", "Meta Ads", "Microsoft Ads"] as const;
const CHANNEL_COLORS: Record<string, string> = {
  "Google Ads": "var(--color-chart-1)",
  "Meta Ads": "var(--color-chart-2)",
  "Microsoft Ads": "var(--color-chart-3)",
};
const WHAT_IF_PRESETS = [
  { name: "Conservative (−20% all)", multiplier: 0.8 },
  { name: "Base (0%)", multiplier: 1 },
  { name: "Aggressive (+30% all)", multiplier: 1.3 },
];

function buildWhatIfScenarios(): WhatIfScenarioInput[] {
  return WHAT_IF_PRESETS.map((preset) => ({
    name: preset.name,
    budgetMultipliers: Object.fromEntries(CHANNELS.map((channel) => [channel, preset.multiplier])),
  }));
}

function SimulatorPage() {
  const { rows } = useData();
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [budgets, setBudgets] = useState<Record<string, number>>({});
  const [apiSims, setApiSims] = useState<SimChannelResult[] | null>(null);
  const [apiSimError, setApiSimError] = useState<string | null>(null);
  const [decisionSupport, setDecisionSupport] = useState<DecisionSupportResponse | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [whatIfScenarios, setWhatIfScenarios] = useState<WhatIfScenarioInput[]>([]);
  const [selectedWhatIfMultiplier, setSelectedWhatIfMultiplier] = useState(1);
  const [targetRevenueDraft, setTargetRevenueDraft] = useState("");
  const [targetRoasDraft, setTargetRoasDraft] = useState("");
  const [targets, setTargets] = useState<{ targetRevenue?: number; targetRoas?: number }>({});
  const [curveChannel, setCurveChannel] = useState<(typeof CHANNELS)[number]>("Google Ads");
  const [spendCurve, setSpendCurve] = useState<SpendCurveResponse | null>(null);

  const baselines = useMemo(() => {
    if (!rows.length) return null;
    const dates = [...new Set(rows.map((row) => row.date))].sort();
    const recentDates = new Set(dates.slice(-30));
    const recentRows = rows.filter((row) => recentDates.has(row.date));
    return Object.fromEntries(
      CHANNELS.map((channel) => {
        const channelRows = recentRows.filter((row) => row.channel === channel);
        const spend = channelRows.reduce((sum, row) => sum + row.spend, 0);
        const activeDays = Math.max(1, new Set(channelRows.map((row) => row.date)).size);
        return [channel, { dailySpend: spend / activeDays }];
      }),
    ) as Record<string, { dailySpend: number }>;
  }, [rows]);

  const totalBudget = useCallback(
    (channel: string) =>
      budgets[channel] ?? Math.round((baselines?.[channel]?.dailySpend ?? 0) * horizon),
    [baselines, budgets, horizon],
  );

  const budgetPayload = useMemo(
    () => Object.fromEntries(CHANNELS.map((channel) => [channel, totalBudget(channel)])),
    [totalBudget],
  );

  useEffect(() => {
    if (rows.length > 0 && baselines && whatIfScenarios.length === 0) {
      setSelectedWhatIfMultiplier(1);
      setWhatIfScenarios(buildWhatIfScenarios());
    }
  }, [baselines, rows.length, whatIfScenarios.length]);

  const baselineSims = useMemo<SimChannelResult[]>(() => {
    if (!rows.length || !baselines) return [];
    const dates = [...new Set(rows.map((row) => row.date))].sort();
    const recentDates = new Set(dates.slice(-Math.min(30, dates.length)));
    const recentRows = rows.filter((row) => recentDates.has(row.date));
    return CHANNELS.map((channel) => {
      const channelRows = recentRows.filter((row) => row.channel === channel);
      const activeDays = Math.max(1, new Set(channelRows.map((row) => row.date)).size);
      const baselineDailySpend = channelRows.reduce((sum, row) => sum + row.spend, 0) / activeDays;
      const baselineDailyRevenue =
        channelRows.reduce((sum, row) => sum + row.revenue, 0) / activeDays;
      const baselineTotalSpend = baselineDailySpend * horizon;
      const baselineRevenue = baselineDailyRevenue * horizon;
      const newTotalSpend = totalBudget(channel);
      const spendRatio = baselineTotalSpend > 0 ? newTotalSpend / baselineTotalSpend : 1;
      const projectedRevenue = baselineRevenue * Math.pow(Math.max(0, spendRatio), 0.85);
      return {
        channel,
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
  }, [baselines, horizon, rows, totalBudget]);

  useEffect(() => {
    if (!rows.length || !baselines) return;
    let active = true;
    setApiSimError(null);
    simulateBudgetsApi(rows, horizon, budgetPayload)
      .then((response) => {
        if (active) {
          setApiSims(response.channels);
        }
      })
      .catch((error: Error) => {
        if (active) {
          setApiSims(null);
          setApiSimError(error.message);
        }
      });
    return () => {
      active = false;
    };
  }, [baselines, budgetPayload, horizon, rows]);

  useEffect(() => {
    if (!rows.length || !baselines) return;
    let active = true;
    setDecisionError(null);
    setDecisionSupport(null);
    decisionSupportApi(rows, horizon, budgetPayload, targets, whatIfScenarios)
      .then((response) => {
        if (active) setDecisionSupport(response);
      })
      .catch((error: Error) => {
        if (!active) return;
        setDecisionSupport(null);
        setDecisionError(error.message);
      });
    return () => {
      active = false;
    };
  }, [baselines, budgetPayload, horizon, rows, targets, whatIfScenarios]);

  useEffect(() => {
    if (!rows.length || !baselines) return;
    let active = true;
    fetchSpendCurveApi(rows, curveChannel, horizon, totalBudget(curveChannel))
      .then((response) => {
        if (active) setSpendCurve(response);
      })
      .catch(() => {
        if (active) setSpendCurve(null);
      });
    return () => {
      active = false;
    };
  }, [baselines, curveChannel, horizon, rows, totalBudget]);

  if (!rows.length || !baselines) {
    return (
      <>
        <PageHeader title="Budget simulator" />
        <EmptyState />
      </>
    );
  }

  const sims = apiSims ?? baselineSims;
  const totalNewSpend = sims.reduce((sum, item) => sum + item.newTotalSpend, 0);
  const totalBaseSpend = sims.reduce((sum, item) => sum + item.baselineTotalSpend, 0);
  const totalProjectedRevenue = sims.reduce((sum, item) => sum + item.projectedRevenue, 0);
  const totalLowerRevenue = sims.reduce((sum, item) => sum + item.projectedRevenueLower, 0);
  const totalUpperRevenue = sims.reduce((sum, item) => sum + item.projectedRevenueUpper, 0);
  const totalBaseRevenue = sims.reduce((sum, item) => sum + item.baselineRevenue, 0);
  const projectedRoas = totalNewSpend > 0 ? totalProjectedRevenue / totalNewSpend : 0;
  const baselineRoas = totalBaseSpend > 0 ? totalBaseRevenue / totalBaseSpend : 0;
  const revenueChangePct = pctChange(totalProjectedRevenue, totalBaseRevenue);
  const roasChangePct = pctChange(projectedRoas, baselineRoas);
  const sliderChannels: BudgetSliderChannel[] = CHANNELS.map((channel) => {
    const sim = sims.find((item) => item.channel === channel);
    return {
      name: channel,
      color: CHANNEL_COLORS[channel],
      baselineTotal: Math.max(1, (baselines[channel]?.dailySpend ?? 0) * horizon),
      projectedRevenue: sim?.projectedRevenue,
      projectedRoas: sim?.projectedRoas,
    };
  });

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
        CHANNELS.map((channel) => [
          channel,
          Math.max(0, Math.round((baselines[channel]?.dailySpend ?? 0) * horizon * multiplier)),
        ]),
      ),
    );
  }

  function retrySimulation() {
    setApiSimError(null);
    setApiSims(null);
    simulateBudgetsApi(rows, horizon, budgetPayload)
      .then((response) => {
        setApiSims(response.channels);
      })
      .catch((error: Error) => {
        setApiSims(null);
        setApiSimError(error.message);
      });
  }

  function runWhatIfPreset(multiplier: number) {
    setSelectedWhatIfMultiplier(multiplier);
    setWhatIfScenarios(buildWhatIfScenarios());
    applyBudgetScenario(multiplier);
  }

  return (
    <>
      <PageHeader
        title="Budget simulator"
        description="Live budget planning for Google Ads, Meta Ads and Microsoft Ads."
      />

      {apiSimError && !apiSims && (
        <Card className="mb-6 border-warning/40 bg-warning/5 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-warning/15 text-warning">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">
                    Forecast backend unavailable — showing local estimate
                  </h3>
                  <Badge variant="outline" className="border-warning/50 text-warning">
                    Local fallback
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  Tip: run <code>npm run api</code> to start the backend.
                </p>
              </div>
            </div>
            <Button type="button" variant="outline" onClick={retrySimulation}>
              Retry
            </Button>
          </div>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="bg-gradient-card border-border/60 p-6 lg:col-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Channel budgets</h3>
              <p className="text-xs text-muted-foreground">Set spend for the next {horizon} days</p>
            </div>
            <Select
              value={String(horizon)}
              onValueChange={(value) => setHorizon(Number(value) as 30 | 60 | 90)}
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

          <div className="mt-6">
            <BudgetSliders
              channels={sliderChannels}
              budgets={budgetPayload}
              onChange={(channel, value) =>
                setBudgets((current) => ({ ...current, [channel]: value }))
              }
            />
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
              {[0.9, 1.1, 1.2, 1.5].map((multiplier) => (
                <Button
                  key={multiplier}
                  type="button"
                  variant="outline"
                  className="h-8 text-xs"
                  onClick={() => applyBudgetScenario(multiplier)}
                >
                  {multiplier < 1 ? "-10%" : `+${Math.round((multiplier - 1) * 100)}%`}
                </Button>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={() => setBudgets({})}
            className="mt-6 w-full rounded-md border border-border/60 bg-background/40 px-3 py-2 text-xs font-medium text-muted-foreground transition hover:bg-background/80 hover:text-foreground"
          >
            Reset to baseline
          </button>

          <div className="mt-6 rounded-lg border border-border/40 bg-background/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Spend efficiency analysis
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Revenue response and diminishing returns curve.
                </p>
              </div>
              <Select
                value={curveChannel}
                onValueChange={(value) => setCurveChannel(value as (typeof CHANNELS)[number])}
              >
                <SelectTrigger className="h-8 w-[150px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CHANNELS.map((channel) => (
                    <SelectItem key={channel} value={channel}>
                      {channel}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <SpendCurveChart
              data={spendCurve?.curve ?? []}
              currentSpend={totalBudget(curveChannel)}
              saturationSpend={spendCurve?.saturation_spend}
              marginalRoas={spendCurve?.marginal_roas}
            />
          </div>
        </Card>

        <SimulatorResultsPanel
          sims={sims}
          horizon={horizon}
          totalNewSpend={totalNewSpend}
          totalBaseSpend={totalBaseSpend}
          totalProjectedRevenue={totalProjectedRevenue}
          totalLowerRevenue={totalLowerRevenue}
          totalUpperRevenue={totalUpperRevenue}
          totalBaseRevenue={totalBaseRevenue}
          projectedRoas={projectedRoas}
          baselineRoas={baselineRoas}
          revenueChangePct={revenueChangePct}
          roasChangePct={roasChangePct}
          channelColors={CHANNEL_COLORS}
          channelHealth={decisionSupport?.channelHealth}
        />
      </div>

      {decisionError && (
        <Card className="mt-6 border-warning/40 bg-warning/5 p-4 text-sm text-warning">
          Decision-support engine unavailable: {decisionError}
        </Card>
      )}

      {decisionSupport && (
        <DecisionSupportPanel
          optimizer={decisionSupport.optimizer}
          whatIf={decisionSupport.scenarios}
          riskAlerts={decisionSupport.risks}
          opportunityAlerts={decisionSupport.opportunities}
          channelHealth={decisionSupport.channelHealth}
          currentRevenue={totalProjectedRevenue}
          currentRoas={projectedRoas}
          horizon={horizon}
          targetRevenueDraft={targetRevenueDraft}
          targetRoasDraft={targetRoasDraft}
          onTargetRevenueChange={setTargetRevenueDraft}
          onTargetRoasChange={setTargetRoasDraft}
          onApplyTargets={applyTargets}
        />
      )}

      <Card className="bg-gradient-card border-border/60 mt-6 min-w-0 overflow-hidden p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold">What-If Scenarios</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Compare conservative, base and aggressive budget moves with the decision-support
              engine.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {WHAT_IF_PRESETS.map((preset) => (
              <Button
                key={preset.name}
                type="button"
                variant="outline"
                className={`h-8 text-xs ${
                  selectedWhatIfMultiplier === preset.multiplier
                    ? "border-primary bg-muted text-foreground"
                    : ""
                }`}
                onClick={() => runWhatIfPreset(preset.multiplier)}
              >
                {preset.name}
              </Button>
            ))}
          </div>
        </div>

        {decisionSupport?.scenarios?.length ? (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-[560px] w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Scenario</th>
                  <th className="px-3 py-2 text-right">Projected revenue</th>
                  <th className="px-3 py-2 text-right">Projected ROAS</th>
                  <th className="py-2 pl-3 text-right">Revenue delta</th>
                </tr>
              </thead>
              <tbody>
                {decisionSupport.scenarios.map((scenario) => (
                  <tr key={scenario.name} className="border-b border-border/40 last:border-0">
                    <td className="py-2 pr-3 font-medium">{scenario.name}</td>
                    <td className="px-3 py-2 text-right">
                      {fmtCurrency(scenario.projectedRevenue)}
                    </td>
                    <td className="px-3 py-2 text-right">{fmtRoas(scenario.projectedRoas)}</td>
                    <td className="py-2 pl-3 text-right">
                      {scenario.revenueDeltaPct >= 0 ? "+" : ""}
                      {scenario.revenueDeltaPct.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !decisionSupport && whatIfScenarios.length > 0 ? (
          <p className="mt-4 text-sm text-muted-foreground">Loading scenario comparisons...</p>
        ) : (
          <p className="mt-4 text-sm text-muted-foreground">
            Select a preset to request scenario comparisons from the backend.
          </p>
        )}
      </Card>
    </>
  );
}

function pctChange(current: number, previous: number) {
  return previous > 0 ? ((current - previous) / previous) * 100 : 0;
}
