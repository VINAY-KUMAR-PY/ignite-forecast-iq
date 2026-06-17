import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useData } from "@/lib/data-store";
import { filterRows, forecastRevenue, forecastRoas } from "@/lib/forecasting";
import { fmtCompact, fmtCurrency, fmtDate, fmtRoas } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";

export const Route = createFileRoute("/app/forecast")({
  head: () => ({ meta: [{ title: "Forecasting · ForecastIQ" }] }),
  component: ForecastPage,
});

type Level = "overall" | "channel" | "campaign_type" | "campaign";

function ForecastPage() {
  const { rows } = useData();
  const [horizon, setHorizon] = useState<30 | 60 | 90>(30);
  const [level, setLevel] = useState<Level>("overall");
  const [value, setValue] = useState<string>("");

  const options = useMemo(() => {
    if (level === "overall") return [];
    const key = level === "channel" ? "channel" : level === "campaign_type" ? "campaign_type" : "campaign_name";
    return [...new Set(rows.map((r) => r[key]))].sort();
  }, [rows, level]);

  const filtered = useMemo(
    () => filterRows(rows, { level, value: level === "overall" ? undefined : value || options[0] }),
    [rows, level, value, options],
  );

  const revFc = useMemo(() => forecastRevenue(filtered, horizon), [filtered, horizon]);
  const roasFc = useMemo(() => forecastRoas(filtered, horizon), [filtered, horizon]);

  if (!rows.length) return (<><PageHeader title="Forecasting" /><EmptyState /></>);

  const forecastRev = revFc.filter((p) => !p.historical);
  const forecastRoasOnly = roasFc.filter((p) => !p.historical);
  const expectedRev = forecastRev.reduce((s, p) => s + p.value, 0);
  const lowerRev = forecastRev.reduce((s, p) => s + p.lower, 0);
  const upperRev = forecastRev.reduce((s, p) => s + p.upper, 0);
  const avgRoasFc = forecastRoasOnly.length ? forecastRoasOnly.reduce((s, p) => s + p.value, 0) / forecastRoasOnly.length : 0;

  // chart data — sample historicals
  const revData = sampleSeries(revFc, 180);
  const roasData = sampleSeries(roasFc, 180);

  return (
    <>
      <PageHeader
        title="Forecasting"
        description="Trend + weekly-seasonality model with 95% confidence intervals."
      />

      <Card className="bg-gradient-card border-border/60 mb-6 p-5">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Horizon</label>
            <Select value={String(horizon)} onValueChange={(v) => setHorizon(Number(v) as 30 | 60 | 90)}>
              <SelectTrigger className="mt-2"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="30">30 days</SelectItem>
                <SelectItem value="60">60 days</SelectItem>
                <SelectItem value="90">90 days</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Level</label>
            <Select value={level} onValueChange={(v) => { setLevel(v as Level); setValue(""); }}>
              <SelectTrigger className="mt-2"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="overall">Overall business</SelectItem>
                <SelectItem value="channel">Channel</SelectItem>
                <SelectItem value="campaign_type">Campaign type</SelectItem>
                <SelectItem value="campaign">Campaign</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Filter</label>
            <Select value={value || options[0] || ""} onValueChange={setValue} disabled={level === "overall"}>
              <SelectTrigger className="mt-2"><SelectValue placeholder={level === "overall" ? "All data" : "Select..."} /></SelectTrigger>
              <SelectContent>
                {options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label={`Expected revenue (${horizon}d)`} value={fmtCurrency(expectedRev)} icon={LineIcon} />
        <KpiCard label="Lower bound" value={fmtCurrency(lowerRev)} icon={LineIcon} hint="95% CI" />
        <KpiCard label="Upper bound" value={fmtCurrency(upperRev)} icon={LineIcon} hint="95% CI" />
        <KpiCard label="Avg forecast ROAS" value={fmtRoas(avgRoasFc)} icon={Target} />
      </div>

      <div className="mt-6 grid gap-4">
        <Card className="bg-gradient-card border-border/60 p-5">
          <div className="mb-3">
            <h3 className="text-sm font-semibold">Revenue forecast</h3>
            <p className="text-xs text-muted-foreground">Historical + projected with 95% confidence band</p>
          </div>
          <ResponsiveContainer width="100%" height={340}>
            <AreaChart data={revData} margin={{ left: -10, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="band" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={fmtDate} stroke="var(--color-muted-foreground)" fontSize={11} minTickGap={50} />
              <YAxis stroke="var(--color-muted-foreground)" fontSize={11} tickFormatter={(v) => fmtCompact(v as number)} />
              <Tooltip content={<TT formatter={fmtCurrency} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="upper" stroke="none" fill="url(#band)" name="Upper bound" />
              <Area type="monotone" dataKey="lower" stroke="none" fill="var(--color-background)" name="Lower bound" />
              <Line type="monotone" dataKey="historical" stroke="var(--color-chart-2)" strokeWidth={2} dot={false} name="Historical" />
              <Line type="monotone" dataKey="forecast" stroke="var(--color-chart-1)" strokeWidth={2} strokeDasharray="5 4" dot={false} name="Forecast" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card className="bg-gradient-card border-border/60 p-5">
          <div className="mb-3">
            <h3 className="text-sm font-semibold">ROAS forecast</h3>
            <p className="text-xs text-muted-foreground">Daily blended ROAS projection</p>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={roasData} margin={{ left: -10, right: 8, top: 8 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={fmtDate} stroke="var(--color-muted-foreground)" fontSize={11} minTickGap={50} />
              <YAxis stroke="var(--color-muted-foreground)" fontSize={11} tickFormatter={(v) => `${(v as number).toFixed(1)}x`} />
              <Tooltip content={<TT formatter={(v: number) => `${v.toFixed(2)}x`} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="historical" stroke="var(--color-chart-3)" strokeWidth={2} dot={false} name="Historical" />
              <Line type="monotone" dataKey="forecast" stroke="var(--color-chart-2)" strokeWidth={2} strokeDasharray="5 4" dot={false} name="Forecast" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </>
  );
}

function sampleSeries(points: { date: string; value: number; lower: number; upper: number; historical?: boolean }[], maxHistorical: number) {
  const hist = points.filter((p) => p.historical);
  const fc = points.filter((p) => !p.historical);
  const step = Math.max(1, Math.floor(hist.length / maxHistorical));
  const sampled = hist.filter((_, i) => i % step === 0 || i === hist.length - 1);
  return [
    ...sampled.map((p) => ({ date: p.date, historical: p.value, forecast: null as number | null, lower: null as number | null, upper: null as number | null })),
    ...fc.map((p) => ({ date: p.date, historical: null as number | null, forecast: p.value, lower: p.lower, upper: p.upper })),
  ];
}

function TT({ active, payload, label, formatter }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <div className="font-medium">{label ? fmtDate(label) : ""}</div>
      {payload.filter((p: any) => p.value != null).map((p: any) => (
        <div key={p.dataKey} className="mt-1 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="capitalize text-muted-foreground">{p.dataKey}:</span>
          <span className="font-medium">{formatter ? formatter(p.value) : p.value}</span>
        </div>
      ))}
    </div>
  );
}
