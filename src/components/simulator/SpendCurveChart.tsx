import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtCompact, fmtCurrency, fmtRoas } from "@/lib/format";

type SpendCurvePoint = { spend: number; revenue: number; roas?: number };
type TooltipPayload = { dataKey: string; name?: string; color: string; value: number };

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

  return (
    <>
      <div className="mt-4 h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ left: -12, right: 8, top: 8 }}>
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
            <Line
              type="monotone"
              dataKey="revenue"
              name="Revenue"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {marginalRoas !== undefined && (
        <p className="mt-3 text-xs text-muted-foreground">
          Estimated marginal ROAS at current spend:{" "}
          <span className="font-semibold text-foreground">{fmtRoas(marginalRoas)}</span>
        </p>
      )}
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
      {payload.map((item) => (
        <div key={item.dataKey} className="mt-1 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
          <span className="text-muted-foreground">{item.name ?? item.dataKey}:</span>
          <span className="font-medium">{fmtCurrency(item.value)}</span>
        </div>
      ))}
    </div>
  );
}
