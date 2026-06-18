import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { LineChart as LineIcon, Target } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
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
import { fetchForecastApi, type ForecastApiResponse } from "@/lib/backend-api";
import { fmtCompact, fmtCurrency, fmtDate, fmtRoas } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";
import type { CampaignRow, ForecastPoint } from "@/lib/types";

export const Route = createFileRoute("/app/forecast")({
  head: () => ({ meta: [{ title: "Forecasting · ForecastIQ" }] }),
  component: ForecastPage,
});

type Level = "overall" | "channel" | "campaign_type" | "campaign";
type ForecastTarget = "revenue" | "roas";

function ForecastPage() {
  const { rows } = useData();
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [level, setLevel] = useState<Level>("overall");
  const [value, setValue] = useState<string>("");
  const [apiForecast, setApiForecast] = useState<ForecastApiResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

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

  // chart data — sample historicals
  const revData = sampleSeries(revFc, 180);
  const roasData = sampleSeries(roasFc, 180);
  const diagnostics = apiForecast?.summary.diagnostics;

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

      <Card className="bg-gradient-card border-border/60 mb-6 p-5">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Horizon
            </label>
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
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Level
            </label>
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
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Filter
            </label>
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
        <KpiCard label="Avg forecast ROAS" value={fmtRoas(avgRoasFc)} icon={Target} />
      </div>

      <div className="mt-6 grid gap-4">
        <Card className="bg-gradient-card border-border/60 p-5">
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
          <ResponsiveContainer width="100%" height={340}>
            <AreaChart data={revData} margin={{ left: -10, right: 8, top: 8 }}>
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
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card className="bg-gradient-card border-border/60 p-5">
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
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={roasData} margin={{ left: -10, right: 8, top: 8 }}>
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
            </AreaChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {diagnostics && (
        <Card
          data-testid="model-diagnostics"
          className="mt-6 bg-gradient-card border-border/60 p-5"
        >
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">Model diagnostics</h3>
              <p className="text-xs text-muted-foreground">
                Fit quality, interval coverage and top XGBoost drivers for this forecast segment.
              </p>
            </div>
            <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {diagnostics.trainingDays} training days
            </span>
          </div>
          <div className="grid gap-4 lg:grid-cols-4">
            <DiagnosticStat
              label="Revenue MAPE"
              value={`${diagnostics.revenueFitMapePct.toFixed(1)}%`}
            />
            <DiagnosticStat label="ROAS MAPE" value={`${diagnostics.roasFitMapePct.toFixed(1)}%`} />
            <DiagnosticStat
              label="Revenue coverage"
              value={`${diagnostics.revenueIntervalCoveragePct.toFixed(0)}%`}
            />
            <DiagnosticStat
              label="ROAS coverage"
              value={`${diagnostics.roasIntervalCoveragePct.toFixed(0)}%`}
            />
          </div>
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <FeatureList title="Revenue drivers" features={diagnostics.topRevenueFeatures} />
            <FeatureList title="ROAS drivers" features={diagnostics.topRoasFeatures} />
          </div>
        </Card>
      )}
    </>
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

function DiagnosticStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/40 bg-background/40 p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

function FeatureList({
  title,
  features,
}: {
  title: string;
  features: Array<{ feature: string; importance: number }>;
}) {
  return (
    <div className="rounded-lg border border-border/40 bg-background/40 p-4">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h4>
      <div className="mt-3 space-y-2">
        {features.map((feature) => (
          <div key={feature.feature}>
            <div className="mb-1 flex items-center justify-between gap-3 text-xs">
              <span className="capitalize">{feature.feature.replaceAll("_", " ")}</span>
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

function sampleSeries(
  points: { date: string; value: number; lower: number; upper: number; historical?: boolean }[],
  maxHistorical: number,
) {
  const hist = points.filter((p) => p.historical);
  const fc = points.filter((p) => !p.historical);
  const step = Math.max(1, Math.floor(hist.length / maxHistorical));
  const sampled = hist.filter((_, i) => i % step === 0 || i === hist.length - 1);
  return [
    ...sampled.map((p) => ({
      date: p.date,
      historical: p.value,
      forecast: null as number | null,
      lower: null as number | null,
      upper: null as number | null,
      range: null as [number, number] | null,
    })),
    ...fc.map((p) => ({
      date: p.date,
      historical: null as number | null,
      forecast: p.value,
      lower: p.lower,
      upper: p.upper,
      range: [p.lower, p.upper] as [number, number],
    })),
  ];
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
