import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  Brain,
  Lightbulb,
  LineChart as LineIcon,
  ListChecks,
  Target,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ModelPathConfidenceBadge } from "@/components/model-path-confidence-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useData } from "@/lib/data-store";
import { aggregateDaily, filterRows } from "@/lib/forecasting";
import {
  fetchForecastApi,
  fetchModelValidationApi,
  type AccuracyMetrics,
  type ForecastApiResponse,
  type ModelValidationResponse,
} from "@/lib/backend-api";
import { fmtCompact, fmtCurrency, fmtDate, fmtRoas } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";
import type { CampaignRow, ForecastPoint } from "@/lib/types";

export const Route = createFileRoute("/app/forecast")({
  head: () => ({ meta: [{ title: "Forecasting · ForecastIQ" }] }),
  component: ForecastPage,
});

type Level = "overall" | "channel" | "campaign_type" | "campaign";
type ForecastTarget = "revenue" | "roas";

export function ForecastPage() {
  const { rows } = useData();
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [level, setLevel] = useState<Level>("overall");
  const [value, setValue] = useState<string>("");
  const [apiForecast, setApiForecast] = useState<ForecastApiResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [modelValidation, setModelValidation] = useState<ModelValidationResponse | null>(null);
  const [modelValidationError, setModelValidationError] = useState<string | null>(null);

  const options = useMemo(() => {
    if (level === "overall") return [];
    const key =
      level === "channel"
        ? "channel"
        : level === "campaign_type"
          ? "campaign_type"
          : "campaign_name";
    return [...new Set(rows.map((r) => r[key]))].sort();
  }, [rows, level]);

  const selectedValue = level === "overall" ? undefined : value || options[0];

  const filtered = useMemo(
    () => filterRows(rows, { level, value: selectedValue }),
    [rows, level, selectedValue],
  );

  const fallbackRevFc = useMemo(
    () => lightweightTrendForecast(filtered, horizon, "revenue"),
    [filtered, horizon],
  );
  const fallbackRoasFc = useMemo(
    () => lightweightTrendForecast(filtered, horizon, "roas"),
    [filtered, horizon],
  );

  useEffect(() => {
    if (!rows.length || (level !== "overall" && !selectedValue)) {
      setApiForecast(null);
      return;
    }
    let active = true;
    setApiError(null);
    setApiForecast(null);
    fetchForecastApi(rows, horizon, level, selectedValue)
      .then((response) => {
        if (!active) return;
        setApiForecast(response);
      })
      .catch((error: Error) => {
        if (!active) return;
        setApiForecast(null);
        setApiError(error.message);
      });
    return () => {
      active = false;
    };
  }, [rows, horizon, level, selectedValue]);

  useEffect(() => {
    if (!rows.length) return;
    let active = true;
    setModelValidationError(null);
    fetchModelValidationApi()
      .then((response) => {
        if (active) setModelValidation(response);
      })
      .catch((error: Error) => {
        if (active) setModelValidationError(error.message);
      });
    return () => {
      active = false;
    };
  }, [rows.length]);

  const revFc = apiForecast?.revenue ?? fallbackRevFc;
  const roasFc = apiForecast?.roas ?? fallbackRoasFc;

  if (!rows.length)
    return (
      <>
        <PageHeader title="Forecasting" />
        <EmptyState />
      </>
    );

  const forecastRev = revFc.filter((p) => !p.historical);
  const forecastRoasOnly = roasFc.filter((p) => !p.historical);
  const expectedRev = forecastRev.reduce((s, p) => s + p.value, 0);
  const lowerRev = forecastRev.reduce((s, p) => s + p.lower, 0);
  const upperRev = forecastRev.reduce((s, p) => s + p.upper, 0);
  const avgRoasFc = forecastRoasOnly.length
    ? forecastRoasOnly.reduce((s, p) => s + p.value, 0) / forecastRoasOnly.length
    : 0;
  const summaryRoas = apiForecast?.summary.avgRoas ?? avgRoasFc;
  const revenueIntervalWidth = upperRev - lowerRev;
  const revenueIntervalWidthPct = expectedRev > 0 ? (revenueIntervalWidth / expectedRev) * 100 : 0;
  const forecastConfidence = revenueIntervalWidthPct > 25 ? "medium" : "high";
  const avgRoasLower = forecastRoasOnly.length
    ? forecastRoasOnly.reduce((s, p) => s + p.lower, 0) / forecastRoasOnly.length
    : 0;
  const avgRoasUpper = forecastRoasOnly.length
    ? forecastRoasOnly.reduce((s, p) => s + p.upper, 0) / forecastRoasOnly.length
    : 0;

  const revData = buildForecastChartSeries(revFc);
  const roasData = buildForecastChartSeries(roasFc);
  const diagnostics = apiForecast?.summary.diagnostics;

  function retryForecast() {
    setApiError(null);
    setApiForecast(null);
    fetchForecastApi(rows, horizon, level, selectedValue)
      .then((response) => {
        setApiForecast(response);
      })
      .catch((error: Error) => {
        setApiForecast(null);
        setApiError(error.message);
      });
  }

  return (
    <>
      <PageHeader
        title="Forecasting"
        description={
          apiError
            ? "Backend unavailable; showing local fallback forecast."
            : "XGBoost backend model with 95% confidence intervals."
        }
      />

      <ModelPathConfidenceBadge />

      {apiError && !apiForecast && (
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
            <Button type="button" variant="outline" onClick={retryForecast}>
              Retry
            </Button>
          </div>
        </Card>
      )}

      <Card className="bg-gradient-card border-border/60 mb-6 min-w-0 p-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="min-w-0">
            <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Horizon
            </div>
            <Select
              value={String(horizon)}
              onValueChange={(v) => setHorizon(Number(v) as 30 | 60 | 90)}
            >
              <SelectTrigger className="mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30 days</SelectItem>
                <SelectItem value="60">60 days</SelectItem>
                <SelectItem value="90">90 days</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Level
            </div>
            <Select
              value={level}
              onValueChange={(v) => {
                setLevel(v as Level);
                setValue("");
              }}
            >
              <SelectTrigger className="mt-2">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="overall">Overall business</SelectItem>
                <SelectItem value="channel">Channel</SelectItem>
                <SelectItem value="campaign_type">Campaign type</SelectItem>
                <SelectItem value="campaign">Campaign</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Filter
            </div>
            <Select
              value={value || options[0] || ""}
              onValueChange={setValue}
              disabled={level === "overall"}
            >
              <SelectTrigger className="mt-2">
                <SelectValue placeholder={level === "overall" ? "All data" : "Select..."} />
              </SelectTrigger>
              <SelectContent>
                {options.map((o) => (
                  <SelectItem key={o} value={o}>
                    {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label={`Expected revenue (${horizon}d)`}
          value={fmtCurrency(expectedRev)}
          icon={LineIcon}
        />
        <KpiCard label="Lower bound" value={fmtCurrency(lowerRev)} icon={LineIcon} hint="95% CI" />
        <KpiCard label="Upper bound" value={fmtCurrency(upperRev)} icon={LineIcon} hint="95% CI" />
        <KpiCard
          label="Avg forecast ROAS"
          value={
            apiForecast?.summary.roasStatus === "not_computable" ? "N/A" : fmtRoas(summaryRoas)
          }
          icon={Target}
          hint={
            apiForecast?.summary.roasStatus === "not_computable"
              ? "Spend absent"
              : `${fmtRoas(apiForecast?.summary.lowerRoas ?? avgRoasLower)} - ${fmtRoas(apiForecast?.summary.upperRoas ?? avgRoasUpper)}`
          }
        />
      </div>

      <Card
        data-testid="confidence-intervals"
        className="mt-6 bg-gradient-card border-border/60 min-w-0 p-5"
      >
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">Confidence interval overview</h3>
            <p className="text-xs text-muted-foreground">
              Forecast spread shown as total revenue range and average ROAS uncertainty.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {revenueIntervalWidthPct.toFixed(1)}% revenue spread
            </span>
            {forecastConfidence === "medium" && (
              <span
                title="Interval width >25% of expected revenue - wider uncertainty due to fewer historical rows for this segment."
                className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-amber-600 dark:text-amber-400"
              >
                Medium confidence
              </span>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <DiagnosticStat
            label="Revenue interval width"
            value={fmtCurrency(revenueIntervalWidth)}
          />
          <DiagnosticStat label="Lower planning case" value={fmtCurrency(lowerRev)} />
          <DiagnosticStat label="Upper upside case" value={fmtCurrency(upperRev)} />
          <DiagnosticStat
            label="ROAS interval"
            value={
              apiForecast?.summary.roasStatus === "not_computable"
                ? "Not computable"
                : `${fmtRoas(apiForecast?.summary.lowerRoas ?? avgRoasLower)} - ${fmtRoas(apiForecast?.summary.upperRoas ?? avgRoasUpper)}`
            }
          />
        </div>
      </Card>

      <ModelValidationPanel validation={modelValidation} error={modelValidationError} />

      <div className="mt-6 grid gap-4">
        <Card className="bg-gradient-card border-border/60 min-w-0 overflow-hidden p-5">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Revenue forecast</h3>
              <p className="text-xs text-muted-foreground">
                Expected forecast with lower &amp; upper bounds
              </p>
            </div>
            <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              95% CI
            </span>
          </div>
          <div
            className="min-w-0 max-w-full overflow-hidden"
            role="img"
            aria-label={`Revenue forecast for ${horizon} days, expected ${fmtCurrency(
              expectedRev,
            )} with planning range ${fmtCurrency(lowerRev)} to ${fmtCurrency(upperRev)}.`}
          >
            <ResponsiveContainer width="100%" height={340}>
              <ComposedChart data={revData} margin={{ left: -10, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="revBand" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.32} />
                    <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0.06} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tickFormatter={fmtDate}
                  stroke="var(--color-muted-foreground)"
                  fontSize={11}
                  minTickGap={50}
                />
                <YAxis
                  stroke="var(--color-muted-foreground)"
                  fontSize={11}
                  tickFormatter={(v) => fmtCompact(v as number)}
                />
                <Tooltip content={<TT formatter={fmtCurrency} />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area
                  type="monotone"
                  dataKey="range"
                  stroke="none"
                  fill="url(#revBand)"
                  name="95% confidence band"
                  isAnimationActive={false}
                  activeDot={false}
                  legendType="rect"
                />
                <Line
                  type="monotone"
                  dataKey="historical"
                  stroke="var(--color-chart-2)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  name="Historical"
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  stroke="var(--color-chart-1)"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  isAnimationActive={false}
                  name="Expected forecast"
                />
                <Line
                  type="monotone"
                  dataKey="upper"
                  stroke="var(--color-chart-1)"
                  strokeWidth={1}
                  strokeDasharray="2 3"
                  strokeOpacity={0.6}
                  dot={false}
                  isAnimationActive={false}
                  name="Upper bound"
                />
                <Line
                  type="monotone"
                  dataKey="lower"
                  stroke="var(--color-chart-1)"
                  strokeWidth={1}
                  strokeDasharray="2 3"
                  strokeOpacity={0.6}
                  dot={false}
                  isAnimationActive={false}
                  name="Lower bound"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="bg-gradient-card border-border/60 min-w-0 overflow-hidden p-5">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">ROAS forecast</h3>
              <p className="text-xs text-muted-foreground">
                Daily blended ROAS with lower &amp; upper bounds
              </p>
            </div>
            <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              95% CI
            </span>
          </div>
          <div
            className="min-w-0 max-w-full overflow-hidden"
            role="img"
            aria-label={
              apiForecast?.summary.roasStatus === "not_computable"
                ? `ROAS forecast for ${horizon} days is not computable because projected spend is unavailable.`
                : `ROAS forecast for ${horizon} days, expected ${fmtRoas(
                    summaryRoas,
                  )} with planning range ${fmtRoas(
                    apiForecast?.summary.lowerRoas ?? avgRoasLower,
                  )} to ${fmtRoas(apiForecast?.summary.upperRoas ?? avgRoasUpper)}.`
            }
          >
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={roasData} margin={{ left: -10, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="roasBand" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-chart-2)" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="var(--color-chart-2)" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tickFormatter={fmtDate}
                  stroke="var(--color-muted-foreground)"
                  fontSize={11}
                  minTickGap={50}
                />
                <YAxis
                  stroke="var(--color-muted-foreground)"
                  fontSize={11}
                  tickFormatter={(v) => `${(v as number).toFixed(1)}x`}
                />
                <Tooltip content={<TT formatter={(v: number) => `${v.toFixed(2)}x`} />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area
                  type="monotone"
                  dataKey="range"
                  stroke="none"
                  fill="url(#roasBand)"
                  name="95% confidence band"
                  isAnimationActive={false}
                  activeDot={false}
                  legendType="rect"
                />
                <Line
                  type="monotone"
                  dataKey="historical"
                  stroke="var(--color-chart-3)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  name="Historical"
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  stroke="var(--color-chart-2)"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  isAnimationActive={false}
                  name="Expected forecast"
                />
                <Line
                  type="monotone"
                  dataKey="upper"
                  stroke="var(--color-chart-2)"
                  strokeWidth={1}
                  strokeDasharray="2 3"
                  strokeOpacity={0.6}
                  dot={false}
                  isAnimationActive={false}
                  name="Upper bound"
                />
                <Line
                  type="monotone"
                  dataKey="lower"
                  stroke="var(--color-chart-2)"
                  strokeWidth={1}
                  strokeDasharray="2 3"
                  strokeOpacity={0.6}
                  dot={false}
                  isAnimationActive={false}
                  name="Lower bound"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {diagnostics && (
        <>
          <Card
            data-testid="accuracy-dashboard"
            className="mt-6 bg-gradient-card border-border/60 min-w-0 p-5"
          >
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Forecast accuracy dashboard</h3>
                <p className="text-xs text-muted-foreground">
                  In-sample model accuracy for revenue and ROAS using MAE, RMSE, MAPE and R2.
                </p>
              </div>
              <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                {diagnostics.trainingDays} training days
              </span>
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <AccuracyPanel title="Revenue model" metrics={diagnostics.revenueAccuracy} money />
              <AccuracyPanel title="ROAS model" metrics={diagnostics.roasAccuracy} />
            </div>
          </Card>

          <Card
            data-testid="explainability-center"
            className="mt-6 bg-gradient-card border-border/60 min-w-0 p-5"
          >
            <div className="mb-4 flex items-center gap-2">
              <Brain className="h-4 w-4 text-primary" />
              <div>
                <h3 className="text-sm font-semibold">Forecast explainability center</h3>
                <p className="text-xs text-muted-foreground">
                  XGBoost feature importance and plain-language driver explanations.
                </p>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ExplanationCard title="Revenue explanation" text={diagnostics.revenueExplanation} />
              <ExplanationCard title="ROAS explanation" text={diagnostics.roasExplanation} />
              <FeatureList title="Top revenue drivers" features={diagnostics.topRevenueFeatures} />
              <FeatureList title="Top ROAS drivers" features={diagnostics.topRoasFeatures} />
              <ShapImportanceList features={diagnostics.shap_importance ?? []} />
            </div>
          </Card>

          <Card
            data-testid="why-this-forecast"
            className="mt-6 bg-gradient-card border-border/60 min-w-0 p-5"
          >
            <div className="mb-4 flex items-center gap-2">
              <Brain className="h-4 w-4 text-primary" />
              <div>
                <h3 className="text-sm font-semibold">Why this forecast?</h3>
                <p className="text-xs text-muted-foreground">
                  Local forecast explainability for this selected segment. These drivers compare the
                  current forecast row with typical historical values, not generic feature
                  importance.
                </p>
              </div>
            </div>
            <p className="mb-4 text-sm leading-relaxed text-muted-foreground">
              {diagnostics.whyThisForecastSummary ||
                "Local driver estimates are unavailable for this segment."}
            </p>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <LocalDriverList
                title="Top positive drivers"
                direction="positive"
                drivers={diagnostics.whyThisForecast ?? []}
              />
              <LocalDriverList
                title="Top negative drivers"
                direction="negative"
                drivers={diagnostics.whyThisForecast ?? []}
              />
            </div>
          </Card>

          <Card
            data-testid="executive-business-brief"
            className="mt-6 bg-gradient-card border-border/60 min-w-0 p-5"
          >
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Executive business brief</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  {diagnostics.businessBrief.summary}
                </p>
              </div>
              <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                model brief
              </span>
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <BriefList
                title="Risks"
                icon={AlertTriangle}
                items={diagnostics.businessBrief.risks}
                tone="destructive"
              />
              <BriefList
                title="Opportunities"
                icon={Lightbulb}
                items={diagnostics.businessBrief.opportunities}
                tone="success"
              />
              <BriefList
                title="Recommended actions"
                icon={ListChecks}
                items={diagnostics.businessBrief.recommendedActions}
                tone="primary"
              />
            </div>
          </Card>

          <Card
            data-testid="model-diagnostics"
            className="mt-6 bg-gradient-card border-border/60 min-w-0 p-5"
          >
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">Model diagnostics</h3>
                <p className="text-xs text-muted-foreground">
                  Fit quality, interval coverage and training depth for this forecast segment.
                </p>
              </div>
              <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                XGBoost diagnostics
              </span>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
              <DiagnosticStat
                label="Revenue MAPE"
                value={`${diagnostics.revenueFitMapePct.toFixed(1)}%`}
              />
              <DiagnosticStat
                label="ROAS MAPE"
                value={`${diagnostics.roasFitMapePct.toFixed(1)}%`}
              />
              <DiagnosticStat
                label="Revenue coverage"
                value={`${diagnostics.revenueIntervalCoveragePct.toFixed(0)}%`}
              />
              <DiagnosticStat
                label="ROAS coverage"
                value={`${diagnostics.roasIntervalCoveragePct.toFixed(0)}%`}
              />
            </div>
          </Card>
        </>
      )}
    </>
  );
}

function ModelValidationPanel({
  validation,
  error,
}: {
  validation: ModelValidationResponse | null;
  error: string | null;
}) {
  return (
    <Card
      data-testid="model-validation-panel"
      className="mt-6 bg-gradient-card border-border/60 min-w-0 overflow-hidden p-5"
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Model Validation</h3>
          <p className="text-xs text-muted-foreground">
            Rolling-origin backtest evidence from the committed report, read without retraining.
          </p>
        </div>
        <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {validation?.modelType ?? "report"}
        </span>
      </div>

      {validation?.rows.length ? (
        <div className="overflow-x-auto">
          <table className="min-w-[720px] w-full text-sm">
            <thead>
              <tr className="border-b border-border/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="py-2 pr-3">Horizon</th>
                <th className="px-3 py-2 text-right">Folds</th>
                <th className="px-3 py-2 text-right">Revenue MAPE</th>
                <th className="px-3 py-2 text-right">Revenue RMSE</th>
                <th className="px-3 py-2 text-right">Coverage</th>
                <th className="px-3 py-2 text-right">ROAS RMSE</th>
                <th className="py-2 pl-3">Revenue verdict</th>
              </tr>
            </thead>
            <tbody>
              {validation.rows.map((row) => (
                <tr key={row.horizonDays} className="border-b border-border/40 last:border-0">
                  <td className="py-2 pr-3 font-medium">{row.horizonDays} days</td>
                  <td className="px-3 py-2 text-right tabular-nums">{row.folds}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.trainedRevenueMape.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {fmtCurrency(row.trainedRevenueRmse)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.trainedRevenueCoverage.toFixed(0)}%
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.trainedRoasRmse.toFixed(2)}
                  </td>
                  <td className="py-2 pl-3 capitalize">{row.revenueWinner.replaceAll("_", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {error
            ? `Model validation report unavailable: ${error}`
            : "Loading rolling-origin validation evidence..."}
        </p>
      )}
    </Card>
  );
}

function lightweightTrendForecast(
  rows: CampaignRow[],
  horizon: 30 | 60 | 90,
  target: ForecastTarget,
): ForecastPoint[] {
  const daily = aggregateDaily(rows);
  if (!daily.length) return [];

  const values = daily.map((day) => (target === "revenue" ? day.revenue : day.roas));
  const historical = daily.map((day, index) => ({
    date: day.date,
    value: values[index],
    lower: values[index],
    upper: values[index],
    historical: true,
  }));

  const recentWindow = Math.min(30, values.length);
  const previousWindow = Math.min(30, Math.max(0, values.length - recentWindow));
  const recent = values.slice(-recentWindow);
  const previous = previousWindow
    ? values.slice(-(recentWindow + previousWindow), -recentWindow)
    : [];
  const recentAverage = mean(recent) || mean(values);
  const previousAverage = previous.length ? mean(previous) : recentAverage;
  const relativeTrend =
    previousAverage > 0 ? (recentAverage - previousAverage) / previousAverage : 0;
  const dailyTrend = clamp(relativeTrend / Math.max(1, recentWindow), -0.015, 0.015);
  const stdDev = standardDeviation(recent, recentAverage);
  const lastDate = new Date(`${daily[daily.length - 1].date}T00:00:00.000Z`);

  let current = recentAverage;
  const forecast: ForecastPoint[] = [];
  for (let day = 1; day <= horizon; day++) {
    const futureDate = new Date(lastDate);
    futureDate.setUTCDate(lastDate.getUTCDate() + day);
    current = Math.max(0, current * (1 + dailyTrend));

    const margin = Math.max(
      stdDev * 1.96 * Math.sqrt(1 + day / 30),
      current * (target === "revenue" ? 0.08 : 0.04),
    );
    forecast.push({
      date: futureDate.toISOString().slice(0, 10),
      value: round2(current),
      lower: round2(Math.max(0, current - margin)),
      upper: round2(current + margin),
    });
  }

  return [...historical, ...forecast];
}

function mean(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function standardDeviation(values: number[], avg: number) {
  if (values.length < 2) return Math.abs(avg) * 0.1;
  const variance =
    values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / Math.max(1, values.length - 1);
  return Math.sqrt(variance);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function round2(value: number) {
  return Math.round(value * 100) / 100;
}

function AccuracyPanel({
  title,
  metrics,
  money = false,
}: {
  title: string;
  metrics: AccuracyMetrics;
  money?: boolean;
}) {
  const formatValue = (value: number) => (money ? fmtCurrency(value) : value.toFixed(2));
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h4>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <MiniMetric label="MAE" value={formatValue(metrics.mae)} />
        <MiniMetric label="RMSE" value={formatValue(metrics.rmse)} />
        <MiniMetric label="MAPE" value={`${metrics.mapePct.toFixed(1)}%`} />
        <MiniMetric label="R2 score" value={metrics.r2Score.toFixed(2)} />
      </div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-0.5 break-words text-base font-semibold">{value}</div>
    </div>
  );
}

function ExplanationCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h4>
      <p className="mt-3 break-words text-sm leading-relaxed text-muted-foreground">{text}</p>
    </div>
  );
}

function BriefList({
  title,
  icon: Icon,
  items,
  tone,
}: {
  title: string;
  icon: LucideIcon;
  items: string[];
  tone: "primary" | "success" | "destructive";
}) {
  const toneClass = {
    primary: "bg-primary/15 text-primary",
    success: "bg-success/15 text-success",
    destructive: "bg-destructive/15 text-destructive",
  }[tone];
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
      <div className="flex items-center gap-2">
        <span className={`grid h-8 w-8 place-items-center rounded-lg ${toneClass}`}>
          <Icon className="h-4 w-4" />
        </span>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </h4>
      </div>
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li key={item} className="text-sm leading-relaxed text-muted-foreground">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DiagnosticStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-lg font-semibold">{value}</div>
    </div>
  );
}

function FeatureList({
  title,
  features,
}: {
  title: string;
  features: Array<{ feature: string; importance: number; label?: string | null }>;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h4>
      <div className="mt-3 space-y-2">
        {features.map((feature) => (
          <div key={feature.feature}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs">
              <span className="min-w-0 break-words capitalize">
                {(feature.label || feature.feature).replaceAll("_", " ")}
              </span>
              <span className="font-medium">{feature.importance.toFixed(1)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary"
                style={{ width: `${Math.min(100, feature.importance)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ShapImportanceList({
  features,
}: {
  features: Array<{
    feature: string;
    shap_value: number;
    importance?: number;
    label?: string;
    direction: "positive" | "negative";
  }>;
}) {
  const maxImpact = Math.max(1, ...features.map((feature) => Math.abs(feature.shap_value)));

  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4 lg:col-span-2">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Global feature attribution
      </h4>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
        SHAP values when available, with a permutation-importance fallback on unsupported runtimes.
      </p>
      <div className="mt-3 space-y-2">
        {features.length ? (
          features.map((feature) => {
            const positive = feature.direction === "positive";
            return (
              <div key={`${feature.feature}-${feature.direction}`}>
                <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                  <span className="min-w-0 break-words capitalize">
                    {(feature.label || feature.feature).replaceAll("_", " ")}
                  </span>
                  <span className={positive ? "text-success" : "text-amber-500"}>
                    {feature.shap_value.toFixed(3)}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className={positive ? "h-full bg-success" : "h-full bg-amber-500"}
                    style={{
                      width: `${Math.max(
                        8,
                        Math.min(100, (Math.abs(feature.shap_value) / maxImpact) * 100),
                      )}%`,
                    }}
                  />
                </div>
              </div>
            );
          })
        ) : (
          <p className="text-sm text-muted-foreground">
            Global attribution is unavailable for this segment, so the page shows local permutation
            drivers instead.
          </p>
        )}
      </div>
    </div>
  );
}

function LocalDriverList({
  title,
  direction,
  drivers,
}: {
  title: string;
  direction: "positive" | "negative";
  drivers: Array<{
    feature: string;
    label: string;
    direction: "positive" | "negative";
    impact: number;
    explanation: string;
  }>;
}) {
  const filtered = drivers.filter((driver) => driver.direction === direction);
  const tone =
    direction === "positive"
      ? "border-success/20 bg-success/10 text-success"
      : "border-destructive/20 bg-destructive/10 text-destructive";
  const barColor = direction === "positive" ? "bg-success" : "bg-destructive";
  const maxImpact = Math.max(1, ...filtered.map((driver) => driver.impact));

  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h4>
      <div className="mt-3 space-y-3">
        {filtered.length ? (
          filtered.map((driver) => (
            <div key={`${driver.direction}-${driver.feature}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="break-words text-sm font-medium">{driver.label}</div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {driver.explanation}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${tone}`}
                >
                  {fmtCurrency(driver.impact)}
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full ${barColor}`}
                  style={{
                    width: `${Math.max(8, Math.min(100, (driver.impact / maxImpact) * 100))}%`,
                  }}
                />
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">
            No material {direction} driver was detected for this forecast row.
          </p>
        )}
      </div>
    </div>
  );
}

const CHART_HISTORY_DAYS = 60;

function buildForecastChartSeries(
  points: { date: string; value: number; lower: number; upper: number; historical?: boolean }[],
) {
  const hist = points.filter((p) => p.historical).slice(-CHART_HISTORY_DAYS);
  const fc = points.filter((p) => !p.historical);
  const lastHistorical = hist.at(-1);
  const alignedForecast = alignForecastDates(fc, lastHistorical?.date);

  const historicalPoints = hist.map((p, index) => {
    const isLastHistorical = index === hist.length - 1;
    return {
      date: p.date,
      historical: p.value,
      forecast: isLastHistorical ? p.value : (null as number | null),
      lower: isLastHistorical ? p.value : (null as number | null),
      upper: isLastHistorical ? p.value : (null as number | null),
      range: isLastHistorical
        ? ([p.value, p.value] as [number, number])
        : (null as [number, number] | null),
    };
  });

  const forecastPoints = alignedForecast.map((p) => ({
    date: p.date,
    historical: null as number | null,
    forecast: p.value,
    lower: p.lower,
    upper: p.upper,
    range: [p.lower, p.upper] as [number, number],
  }));

  return [...historicalPoints, ...forecastPoints];
}

function alignForecastDates(
  forecast: { date: string; value: number; lower: number; upper: number }[],
  lastHistoricalDate?: string,
) {
  if (!lastHistoricalDate) return forecast;
  const base = new Date(`${lastHistoricalDate}T00:00:00.000Z`);
  if (Number.isNaN(base.getTime())) return forecast;

  return forecast.map((point, index) => {
    const nextDate = new Date(base);
    nextDate.setUTCDate(base.getUTCDate() + index + 1);
    return { ...point, date: nextDate.toISOString().slice(0, 10) };
  });
}

type TooltipPayload = {
  dataKey: string;
  color: string;
  value: number | [number, number];
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
      {payload
        .filter((p) => p.value != null)
        .map((p) => {
          const formattedValue = Array.isArray(p.value)
            ? p.value.map((v) => (formatter ? formatter(v) : String(v))).join(" - ")
            : formatter
              ? formatter(p.value)
              : p.value;
          return (
            <div key={p.dataKey} className="mt-1 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
              <span className="capitalize text-muted-foreground">{p.dataKey}:</span>
              <span className="font-medium">{formattedValue}</span>
            </div>
          );
        })}
    </div>
  );
}
