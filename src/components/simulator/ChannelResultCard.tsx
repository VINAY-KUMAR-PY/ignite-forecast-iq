import { Card } from "@/components/ui/card";
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
import { KpiCard } from "@/components/kpi-card";
import type { ChannelHealthScore, SimChannelResult } from "@/lib/backend-api";
import { fmtCompact, fmtCurrency, fmtDate, fmtPct, fmtRoas } from "@/lib/format";

function ChannelResultCard({
  channel,
  projectedRevenue,
  projectedRoas,
  spend,
  efficiency,
  color,
}: {
  channel: string;
  projectedRevenue: number;
  projectedRoas: number;
  spend: number;
  efficiency: number;
  color?: string;
}) {
  return (
    <Card className="border-border/50 bg-background/45 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: color ?? "var(--color-primary)" }}
          />
          <div className="text-sm font-medium">{channel}</div>
        </div>
        <span className="rounded-full border border-border/50 px-2 py-0.5 text-[10px] text-muted-foreground">
          {Math.round(efficiency)}/100
        </span>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 text-xs">
        <div>
          <div className="text-muted-foreground">Spend</div>
          <div className="mt-1 font-semibold">{fmtCurrency(spend)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">Revenue</div>
          <div className="mt-1 font-semibold">{fmtCurrency(projectedRevenue)}</div>
        </div>
        <div>
          <div className="text-muted-foreground">ROAS</div>
          <div className="mt-1 font-semibold">{fmtRoas(projectedRoas)}</div>
        </div>
      </div>
    </Card>
  );
}

type TooltipPayload = { dataKey: string; name?: string; color: string; value: number };
type PieTooltipPayload = { payload?: { name: string; value: number; share: number } };

export function SimulatorResultsPanel({
  sims,
  horizon,
  totalNewSpend,
  totalBaseSpend,
  totalProjectedRevenue,
  totalLowerRevenue,
  totalUpperRevenue,
  totalBaseRevenue,
  projectedRoas,
  baselineRoas,
  revenueChangePct,
  roasChangePct,
  channelColors,
  channelHealth = [],
}: {
  sims: SimChannelResult[];
  horizon: 30 | 60 | 90;
  totalNewSpend: number;
  totalBaseSpend: number;
  totalProjectedRevenue: number;
  totalLowerRevenue: number;
  totalUpperRevenue: number;
  totalBaseRevenue: number;
  projectedRoas: number;
  baselineRoas: number;
  revenueChangePct: number;
  roasChangePct: number;
  channelColors: Record<string, string>;
  channelHealth?: ChannelHealthScore[];
}) {
  const chartData = sims.map((item) => ({
    name: item.channel,
    "Baseline revenue": Math.round(item.baselineRevenue),
    "Projected revenue": Math.round(item.projectedRevenue),
  }));
  const contributionData = sims.map((item) => ({
    name: item.channel,
    value: Math.max(0, Math.round(item.projectedRevenue)),
    color: channelColors[item.channel] ?? "var(--color-primary)",
    share: totalProjectedRevenue > 0 ? item.projectedRevenue / totalProjectedRevenue : 0,
  }));
  const dailyTrend = buildDailyTrend(sims);

  return (
    <div className="space-y-4 lg:col-span-3">
      <div className="grid gap-4 sm:grid-cols-2">
        <KpiCard
          label={`Projected revenue (${horizon}d)`}
          value={fmtCurrency(totalProjectedRevenue)}
          delta={revenueChangePct}
          icon={DollarSign}
          hint={`${fmtCurrency(totalLowerRevenue)} - ${fmtCurrency(totalUpperRevenue)} 95% CI`}
        />
        <KpiCard
          label="Projected blended ROAS"
          value={fmtRoas(projectedRoas)}
          delta={roasChangePct}
          icon={Target}
          hint={`baseline ${fmtRoas(baselineRoas)}`}
        />
        <KpiCard
          label="Total spend"
          value={fmtCurrency(totalNewSpend)}
          icon={Activity}
          hint={`baseline ${fmtCurrency(totalBaseSpend)}`}
        />
        <KpiCard
          label="Revenue lift"
          value={`${revenueChangePct >= 0 ? "+" : ""}${fmtPct(revenueChangePct / 100)}`}
          icon={TrendingUp}
          hint={fmtCurrency(totalProjectedRevenue - totalBaseRevenue)}
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
                {contributionData.map((item) => (
                  <Cell key={item.name} fill={item.color} stroke="var(--color-background)" />
                ))}
              </Pie>
              <Tooltip content={<PieTT />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-2 space-y-1.5">
            {contributionData.map((item) => (
              <div key={item.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
                  <span>{item.name}</span>
                </div>
                <span className="font-medium tabular-nums">{fmtPct(item.share)}</span>
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
                tickFormatter={(value: string) => value.replace(" Ads", "")}
              />
              <YAxis
                stroke="var(--color-muted-foreground)"
                fontSize={11}
                tickFormatter={(value) => fmtCompact(value as number)}
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
          <h3 className="text-sm font-semibold">Forecast trajectory</h3>
          <p className="mb-3 text-xs text-muted-foreground">
            Daily projected revenue across all channels
          </p>
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
                tickFormatter={(value) => fmtCompact(value as number)}
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
        <div className="grid gap-3 md:grid-cols-3">
          {sims.map((item) => (
            <ChannelResultCard
              key={item.channel}
              channel={item.channel}
              projectedRevenue={item.projectedRevenue}
              projectedRoas={item.projectedRoas}
              spend={item.newTotalSpend}
              efficiency={
                channelHealth.find((health) => health.channel === item.channel)?.score ?? 70
              }
              color={channelColors[item.channel]}
            />
          ))}
        </div>
      </Card>
    </div>
  );
}

function buildDailyTrend(sims: SimChannelResult[]) {
  const map = new Map<string, { date: string; revenue: number; lower: number; upper: number }>();
  for (const sim of sims) {
    for (const day of sim.daily) {
      const current = map.get(day.date) ?? { date: day.date, revenue: 0, lower: 0, upper: 0 };
      current.revenue += day.value;
      current.lower += day.lower;
      current.upper += day.upper;
      map.set(day.date, current);
    }
  }
  return [...map.values()].sort((a, b) => (a.date < b.date ? -1 : 1));
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
      {payload.map((item) => (
        <div key={item.dataKey} className="mt-1 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
          <span className="text-muted-foreground">{item.name ?? item.dataKey}:</span>
          <span className="font-medium">{formatter ? formatter(item.value) : item.value}</span>
        </div>
      ))}
    </div>
  );
}

function PieTT({ active, payload }: { active?: boolean; payload?: PieTooltipPayload[] }) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  if (!data) return null;
  return (
    <div className="rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <div className="font-medium">{data.name}</div>
      <div className="mt-1 text-muted-foreground">
        {fmtCurrency(data.value)} - {fmtPct(data.share)}
      </div>
    </div>
  );
}
