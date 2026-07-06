import {
  Area,
  CartesianGrid,
  Line,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtCompact, fmtCurrency, fmtRoas } from "@/lib/format";

type SpendCurvePoint = {
  spend: number;
  revenue: number;
  roas?: number;
  lower_revenue?: number;
  upper_revenue?: number;
};
type ChartPoint = SpendCurvePoint & { confidence_band: [number, number] };
type TooltipPayload = {
  dataKey: string;
  name?: string;
  color: string;
  value: number | [number, number];
};

export function SpendCurveChart({
  data,
  currentSpend,
  saturationSpend = 0,
  marginalRoas,
}: {
  data: SpendCurvePoint[];
  currentSpend: number;
  saturationSpend?: number;
  marginalRoas?: number;
}) {
  if (!data.length) {
    return (
      <p className="mt-4 text-xs text-muted-foreground">
        Move a budget slider to calculate a spend response curve.
      </p>
    );
  }

  const chartData: ChartPoint[] = data.map((point) => {
    const lower = point.lower_revenue ?? point.revenue * 0.85;
    const upper = point.upper_revenue ?? point.revenue * 1.15;
    return {
      ...point,
      lower_revenue: lower,
      upper_revenue: upper,
      confidence_band: [lower, upper],
    };
  });
  const minSpend = Math.min(...chartData.map((point) => point.spend));
  const maxSpend = Math.max(...chartData.map((point) => point.spend));
  const minRevenue = Math.min(...chartData.map((point) => point.lower_revenue ?? point.revenue));
  const maxRevenue = Math.max(...chartData.map((point) => point.upper_revenue ?? point.revenue));

  return (
    <>
      <div
        className="mt-4 h-56 min-w-0 max-w-full overflow-hidden"
        role="img"
        aria-label={`Spend response curve from ${fmtCurrency(minSpend)} to ${fmtCurrency(
          maxSpend,
        )}, with revenue range ${fmtCurrency(minRevenue)} to ${fmtCurrency(maxRevenue)}.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ left: -12, right: 8, top: 8 }}>
            <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
            <XAxis
              dataKey="spend"
              tickFormatter={(value) => fmtCompact(value as number)}
              stroke="var(--color-muted-foreground)"
              fontSize={10}
            />
            <YAxis
              tickFormatter={(value) => fmtCompact(value as number)}
              stroke="var(--color-muted-foreground)"
              fontSize={10}
            />
            <Tooltip content={<CurveTooltip />} />
            <ReferenceLine
              x={currentSpend}
              stroke="var(--color-primary)"
              strokeDasharray="4 4"
              label="Current"
            />
            {saturationSpend > 0 && (
              <ReferenceLine
                x={saturationSpend}
                stroke="var(--color-destructive)"
                strokeDasharray="4 4"
                label="Diminishing returns"
              />
            )}
            <Area
              type="monotone"
              dataKey="confidence_band"
              name="Revenue confidence band"
              stroke="var(--color-chart-1)"
              strokeWidth={0}
              fill="var(--color-chart-1)"
              fillOpacity={0.15}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="revenue"
              name="Revenue"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {marginalRoas !== undefined && (
        <p className="mt-3 text-xs text-muted-foreground">
          Estimated marginal ROAS at current spend:{" "}
          <span className="font-semibold text-foreground">{fmtRoas(marginalRoas)}</span>
        </p>
      )}
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        Shaded band shows estimated uncertainty from historical volatility and segment sample size.
      </p>
    </>
  );
}

function CurveTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <div className="font-medium">Spend {fmtCurrency(Number(label ?? 0))}</div>
      {payload
        .filter((item) => item.dataKey !== "confidence_band")
        .map((item) => (
          <div key={item.dataKey} className="mt-1 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
            <span className="text-muted-foreground">{item.name ?? item.dataKey}:</span>
            <span className="font-medium">{fmtCurrency(Number(item.value))}</span>
          </div>
        ))}
    </div>
  );
}
