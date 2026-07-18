import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Sparkles } from "lucide-react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import {
  BudgetSliders,
  zoneBadgeClass,
  zoneLabel,
  type BudgetSliderChannel,
} from "@/components/simulator/BudgetSliders";
import { SimulatorResultsPanel } from "@/components/simulator/ChannelResultCard";
import { DecisionSupportPanel } from "@/components/simulator/DecisionSupportPanel";
import { SpendCurveChart } from "@/components/simulator/SpendCurveChart";
import { EmptyState } from "@/components/empty-state";
import { ModelPathConfidenceBadge } from "@/components/model-path-confidence-badge";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  type ChannelPlanningZone,
  type DecisionSupportResponse,
  type SimChannelResult,
  type SpendCurveResponse,
  type WhatIfScenarioInput,
} from "@/lib/backend-api";
import { useData } from "@/lib/data-store";
import { allocateBudgetExact, budgetTotal as sumBudgets } from "@/lib/budget-allocation";
import { buildEfficientFrontier, type FrontierPoint } from "@/lib/efficient-frontier";
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
  { name: "Conservative plan (−20%)", multiplier: 0.8 },
  { name: "Current plan", multiplier: 1 },
  { name: "Growth plan (+30%)", multiplier: 1.3 },
];

function buildWhatIfScenarios(
  currentBudgets: Record<string, number>,
  automaticBudgets: Record<string, number>,
): WhatIfScenarioInput[] {
  const presets = WHAT_IF_PRESETS.map((preset) => ({
    name: preset.name,
    budgetMultipliers: Object.fromEntries(CHANNELS.map((channel) => [channel, preset.multiplier])),
  }));
  presets.splice(1, 0, {
    name: "Automatic allocation",
    budgetMultipliers: Object.fromEntries(
      CHANNELS.map((channel) => [
        channel,
        currentBudgets[channel] > 0 ? automaticBudgets[channel] / currentBudgets[channel] : 1,
      ]),
    ),
  });
  return presets;
}

function SimulatorPage() {
  const { rows, markWorkflow, setPlanningSnapshot } = useData();
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [planningMode, setPlanningMode] = useState<"automatic" | "manual">("automatic");
  const [allocationMethod, setAllocationMethod] = useState<"historical" | "optimizer">(
    "historical",
  );
  const [automaticTotal, setAutomaticTotal] = useState<number | null>(null);
  const [optimizerWeights, setOptimizerWeights] = useState<Record<string, number> | null>(null);
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

  const baselineBudgetMap = useMemo(
    () =>
      Object.fromEntries(
        CHANNELS.map((channel) => [
          channel,
          Math.max(0, Math.round((baselines?.[channel]?.dailySpend ?? 0) * horizon * 100) / 100),
        ]),
      ),
    [baselines, horizon],
  );
  const baselineTotalBudget = useMemo(() => sumBudgets(baselineBudgetMap), [baselineBudgetMap]);
  const effectiveAutomaticTotal = automaticTotal ?? baselineTotalBudget;
  const allocationWeights =
    allocationMethod === "optimizer" && optimizerWeights ? optimizerWeights : baselineBudgetMap;
  const automaticBudgets = useMemo(
    () => allocateBudgetExact(effectiveAutomaticTotal, CHANNELS, allocationWeights),
    [allocationWeights, effectiveAutomaticTotal],
  );

  const budgetPayload = useMemo(
    () =>
      planningMode === "automatic"
        ? automaticBudgets
        : Object.fromEntries(CHANNELS.map((channel) => [channel, totalBudget(channel)])),
    [automaticBudgets, planningMode, totalBudget],
  );

  useEffect(() => {
    if (rows.length > 0 && baselines) {
      setWhatIfScenarios(buildWhatIfScenarios(budgetPayload, automaticBudgets));
    }
  }, [automaticBudgets, baselines, budgetPayload, rows.length]);

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
      const newTotalSpend = budgetPayload[channel] ?? 0;
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
  }, [baselines, budgetPayload, horizon, rows]);

  useEffect(() => {
    if (!rows.length || !baselines) return;
    const controller = new AbortController();
    setApiSimError(null);
    simulateBudgetsApi(rows, horizon, budgetPayload, { signal: controller.signal })
      .then((response) => {
        setApiSims(response.channels);
      })
      .catch((error: Error) => {
        if (error.name === "AbortError") return;
        setApiSims(null);
        setApiSimError(error.message);
      });
    return () => controller.abort();
  }, [baselines, budgetPayload, horizon, rows]);

  useEffect(() => {
    if (!rows.length || !baselines || whatIfScenarios.length === 0) return;
    const controller = new AbortController();
    setDecisionError(null);
    setDecisionSupport(null);
    decisionSupportApi(rows, horizon, budgetPayload, targets, whatIfScenarios, {
      signal: controller.signal,
    })
      .then((response) => {
        setDecisionSupport(response);
        markWorkflow("simulate");
        setPlanningSnapshot({
          horizon,
          allocationMode: planningMode,
          budgets: budgetPayload,
          decisionSupport: response,
        });
      })
      .catch((error: Error) => {
        if (error.name === "AbortError") return;
        setDecisionSupport(null);
        setDecisionError(error.message);
      });
    return () => controller.abort();
  }, [
    baselines,
    budgetPayload,
    horizon,
    markWorkflow,
    planningMode,
    rows,
    setPlanningSnapshot,
    targets,
    whatIfScenarios,
  ]);

  useEffect(() => {
    if (!rows.length || !baselines) return;
    const controller = new AbortController();
    fetchSpendCurveApi(rows, curveChannel, horizon, budgetPayload[curveChannel] ?? 0, {
      signal: controller.signal,
    })
      .then((response) => {
        setSpendCurve(response);
      })
      .catch((error: Error) => {
        if (error.name !== "AbortError") setSpendCurve(null);
      });
    return () => controller.abort();
  }, [baselines, budgetPayload, curveChannel, horizon, rows]);

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
  const frontier = buildEfficientFrontier(decisionSupport?.scenarios ?? []);
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
    if (planningMode === "automatic") {
      setAutomaticTotal(Math.max(0, Math.round(baselineTotalBudget * multiplier * 100) / 100));
      return;
    }
    setBudgets(
      Object.fromEntries(
        CHANNELS.map((channel) => [
          channel,
          Math.max(0, Math.round((baselines[channel]?.dailySpend ?? 0) * horizon * multiplier)),
        ]),
      ),
    );
  }

  function switchPlanningMode(nextMode: "automatic" | "manual") {
    if (nextMode === planningMode) return;
    if (nextMode === "manual") {
      setBudgets(budgetPayload);
    } else {
      setAutomaticTotal(sumBudgets(budgetPayload));
    }
    setPlanningMode(nextMode);
  }

  function selectAllocationMethod(nextMethod: "historical" | "optimizer") {
    if (nextMethod === "optimizer") {
      if (!decisionSupport) return;
      setOptimizerWeights(
        Object.fromEntries(
          decisionSupport.optimizer.recommendations.map((item) => [
            item.channel,
            Math.max(0, item.recommendedBudget),
          ]),
        ),
      );
    }
    setAllocationMethod(nextMethod);
  }

  function resetPlanningBudgets() {
    if (planningMode === "automatic") {
      setAutomaticTotal(null);
      setAllocationMethod("historical");
      setOptimizerWeights(null);
    } else {
      setBudgets({});
    }
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
    setWhatIfScenarios(buildWhatIfScenarios(budgetPayload, automaticBudgets));
    applyBudgetScenario(multiplier);
  }

  return (
    <>
      <PageHeader
        title="Budget simulator"
        description="Live budget planning for Google Ads, Meta Ads and Microsoft Ads."
      />

      <ModelPathConfidenceBadge />

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
        <Card className="min-w-0 bg-gradient-card border-border/60 p-6 lg:col-span-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Budget plan</h3>
              <p className="text-xs text-muted-foreground">
                Plan spend for the next {horizon} days
              </p>
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

          <div
            className="mt-5 grid grid-cols-2 rounded-lg border border-border/60 bg-background/40 p-1"
            role="group"
            aria-label="Budget planning mode"
          >
            <button
              type="button"
              aria-pressed={planningMode === "automatic"}
              className={`rounded-md px-3 py-2 text-xs font-medium ${
                planningMode === "automatic"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => switchPlanningMode("automatic")}
            >
              Automatic allocation
            </button>
            <button
              type="button"
              aria-pressed={planningMode === "manual"}
              className={`rounded-md px-3 py-2 text-xs font-medium ${
                planningMode === "manual"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => switchPlanningMode("manual")}
            >
              Manual channel budgets
            </button>
          </div>

          {decisionSupport?.overallPlanZone && (
            <div className="mt-4 rounded-lg border border-border/50 bg-background/40 p-3 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">Overall plan support</span>
                <Badge
                  variant="outline"
                  className={zoneBadgeClass(decisionSupport.overallPlanZone.zone)}
                >
                  {zoneLabel(decisionSupport.overallPlanZone.zone)}
                </Badge>
              </div>
              <p className="mt-2 text-muted-foreground">
                Spend-weighted score{" "}
                {decisionSupport.overallPlanZone.weightedSeverityScore.toFixed(2)}; maximum
                supported total{" "}
                {fmtCurrency(decisionSupport.overallPlanZone.maxSupportedTotalBudget)}.
              </p>
            </div>
          )}

          <div className="mt-6">
            {planningMode === "automatic" ? (
              <AutomaticAllocationPanel
                total={effectiveAutomaticTotal}
                onTotalChange={setAutomaticTotal}
                method={allocationMethod}
                onMethodChange={selectAllocationMethod}
                optimizerAvailable={Boolean(decisionSupport)}
                budgets={budgetPayload}
                historicalBudgets={baselineBudgetMap}
                planningZones={decisionSupport?.planningZones ?? []}
              />
            ) : (
              <BudgetSliders
                channels={sliderChannels}
                budgets={budgetPayload}
                planningZones={decisionSupport?.planningZones}
                onChange={(channel, value) =>
                  setBudgets((current) => ({ ...current, [channel]: value }))
                }
              />
            )}
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
            onClick={resetPlanningBudgets}
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
              currentSpend={budgetPayload[curveChannel] ?? 0}
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
        <Card className="mt-6 border-warning/40 bg-warning/5 p-4 text-sm text-warning" role="alert">
          <p>Decision-support engine unavailable: {decisionError}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            Next step: start the API with <code>npm run api</code>, then change a budget or retry
            the current plan.
          </p>
        </Card>
      )}

      {decisionSupport && (
        <DecisionSupportPanel
          optimizer={decisionSupport.optimizer}
          whatIf={decisionSupport.scenarios}
          riskAlerts={decisionSupport.risks}
          opportunityAlerts={decisionSupport.opportunities}
          channelHealth={decisionSupport.channelHealth}
          simulations={sims}
          planningZones={decisionSupport.planningZones}
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

      <EfficientFrontierPanel
        loading={!decisionSupport && whatIfScenarios.length > 0}
        frontier={frontier}
      />

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

function AutomaticAllocationPanel({
  total,
  onTotalChange,
  method,
  onMethodChange,
  optimizerAvailable,
  budgets,
  historicalBudgets,
  planningZones,
}: {
  total: number;
  onTotalChange: (value: number) => void;
  method: "historical" | "optimizer";
  onMethodChange: (method: "historical" | "optimizer") => void;
  optimizerAvailable: boolean;
  budgets: Record<string, number>;
  historicalBudgets: Record<string, number>;
  planningZones: ChannelPlanningZone[];
}) {
  const historicalTotal = sumBudgets(historicalBudgets);
  return (
    <div data-testid="automatic-allocation" className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label htmlFor="total-planned-budget">Total budget</Label>
          <Input
            id="total-planned-budget"
            type="number"
            min={0}
            step="0.01"
            value={total}
            onChange={(event) => onTotalChange(Math.max(0, Number(event.target.value) || 0))}
            className="mt-2"
          />
        </div>
        <div>
          <Label htmlFor="allocation-method">Allocation method</Label>
          <Select value={method} onValueChange={onMethodChange}>
            <SelectTrigger id="allocation-method" className="mt-2">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="historical">Recent historical spend share</SelectItem>
              <SelectItem value="optimizer" disabled={!optimizerAvailable}>
                Optimizer-recommended share
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-border/50">
        <table className="w-full min-w-[500px] text-xs">
          <caption className="sr-only">
            Automatic channel allocations that sum to the entered total budget
          </caption>
          <thead className="bg-background/60 text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Channel
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Amount
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Share
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Historical
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Evidence
              </th>
            </tr>
          </thead>
          <tbody>
            {CHANNELS.map((channel) => {
              const amount = budgets[channel] ?? 0;
              const evidence = planningZones.find((item) => item.channel === channel);
              return (
                <tr key={channel} className="border-t border-border/40">
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    {channel}
                  </th>
                  <td className="px-3 py-2 text-right">{fmtCurrency(amount)}</td>
                  <td className="px-3 py-2 text-right">
                    {total > 0 ? ((amount / total) * 100).toFixed(1) : "0.0"}%
                  </td>
                  <td className="px-3 py-2 text-right">
                    {historicalTotal > 0
                      ? (((historicalBudgets[channel] ?? 0) / historicalTotal) * 100).toFixed(1)
                      : "No history"}
                    {historicalTotal > 0 ? "%" : ""}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {evidence ? (
                      <Badge variant="outline" className={zoneBadgeClass(evidence.zone)}>
                        {zoneLabel(evidence.zone)}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">Pending</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-border/60 font-semibold">
              <th scope="row" className="px-3 py-2 text-left">
                Total
              </th>
              <td className="px-3 py-2 text-right">{fmtCurrency(sumBudgets(budgets))}</td>
              <td className="px-3 py-2 text-right">100.0%</td>
              <td colSpan={2} />
            </tr>
          </tfoot>
        </table>
      </div>
      {!optimizerAvailable && (
        <p className="text-xs text-muted-foreground">
          Optimizer share becomes available after decision-support evidence loads.
        </p>
      )}
    </div>
  );
}

function pctChange(current: number, previous: number) {
  return previous > 0 ? ((current - previous) / previous) * 100 : 0;
}

function EfficientFrontierPanel({
  frontier,
  loading,
}: {
  frontier: FrontierPoint[];
  loading: boolean;
}) {
  const recommended = frontier.find((point) => point.isRecommended);
  return (
    <Card className="bg-gradient-card border-border/60 mt-6 min-w-0 overflow-hidden p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold">Efficient frontier</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Spend vs revenue tradeoff across deterministic budget scenarios.
          </p>
        </div>
        {recommended && (
          <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary">
            {recommended.name}: balanced option
          </Badge>
        )}
      </div>
      {loading ? (
        <div className="grid h-[260px] place-items-center rounded-lg border border-dashed border-border/60 text-sm text-muted-foreground">
          Loading frontier scenarios...
        </div>
      ) : frontier.length === 0 ? (
        <div className="grid h-[260px] place-items-center rounded-lg border border-dashed border-border/60 text-center text-sm text-muted-foreground">
          Run scenario comparisons to plot the frontier.
        </div>
      ) : (
        <>
          <div
            className="h-[300px] min-w-0"
            role="img"
            aria-label="Efficient frontier chart showing planned spend on the x-axis and expected revenue on the y-axis."
          >
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ left: -12, right: 16, top: 12, bottom: 8 }}>
                <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="totalSpend"
                  name="Planned spend"
                  tickFormatter={(value) => fmtCurrency(Number(value))}
                  stroke="var(--color-muted-foreground)"
                  fontSize={11}
                />
                <YAxis
                  dataKey="projectedRevenue"
                  name="Expected revenue"
                  tickFormatter={(value) => fmtCurrency(Number(value))}
                  stroke="var(--color-muted-foreground)"
                  fontSize={11}
                />
                <ZAxis dataKey="uncertaintyWidthPct" range={[80, 240]} name="Uncertainty width" />
                <Tooltip content={<FrontierTooltip />} cursor={{ strokeDasharray: "3 3" }} />
                <Scatter
                  name="Budget scenarios"
                  data={frontier}
                  fill="var(--color-chart-1)"
                  line={{ stroke: "var(--color-chart-1)", strokeWidth: 1.5 }}
                  shape={(props) => <FrontierDot {...props} />}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {frontier
              .filter(
                (point) =>
                  point.isRecommended ||
                  point.isHighestRevenue ||
                  point.isHighestRoas ||
                  point.isLowestRisk,
              )
              .slice(0, 4)
              .map((point) => (
                <div
                  key={`${point.name}-${point.recommendationLabel}`}
                  className="rounded-lg border border-border/50 bg-background/50 p-3"
                >
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {point.recommendationLabel}
                  </div>
                  <div className="mt-1 text-sm font-medium">{point.name}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {fmtCurrency(point.totalSpend)} spend, {fmtRoas(point.projectedRoas)} ROAS
                  </div>
                </div>
              ))}
          </div>
        </>
      )}
    </Card>
  );
}

function FrontierTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: FrontierPoint }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-popover p-3 text-xs shadow-md">
      <div className="font-semibold text-foreground">{point.name}</div>
      <div className="mt-1 text-muted-foreground">Spend: {fmtCurrency(point.totalSpend)}</div>
      <div className="text-muted-foreground">Revenue: {fmtCurrency(point.projectedRevenue)}</div>
      <div className="text-muted-foreground">ROAS: {fmtRoas(point.projectedRoas)}</div>
      <div className="text-muted-foreground">
        Uncertainty width: {point.uncertaintyWidthPct.toFixed(1)}%
      </div>
      <div className="text-muted-foreground">Risk: {point.riskLevel}</div>
      <div className="mt-1 font-medium text-primary">{point.recommendationLabel}</div>
    </div>
  );
}

function FrontierDot(props: { cx?: number; cy?: number; payload?: FrontierPoint }) {
  const { cx = 0, cy = 0, payload } = props;
  const fill = payload?.isRecommended
    ? "var(--color-primary)"
    : payload?.riskLevel === "high"
      ? "var(--color-destructive)"
      : payload?.riskLevel === "medium"
        ? "var(--color-warning)"
        : "var(--color-chart-1)";
  return (
    <circle
      cx={cx}
      cy={cy}
      r={payload?.isRecommended ? 7 : 5}
      fill={fill}
      stroke="var(--color-background)"
      strokeWidth={2}
    />
  );
}
