import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import type { ChannelPlanningZone, PlanningZone } from "@/lib/backend-api";
import { fmtCurrency, fmtRoas } from "@/lib/format";

export type BudgetSliderChannel = {
  name: string;
  color?: string;
  baselineTotal: number;
  projectedRevenue?: number;
  projectedRoas?: number;
};

export function BudgetSliders({
  channels,
  budgets,
  onChange,
  planningZones = [],
}: {
  channels: BudgetSliderChannel[];
  budgets: Record<string, number>;
  onChange: (channel: string, value: number) => void;
  planningZones?: ChannelPlanningZone[];
}) {
  return (
    <div className="space-y-6">
      {channels.map((channel) => {
        const baseline = Math.max(0, Math.round(channel.baselineTotal));
        const value = budgets[channel.name] ?? baseline;
        const evidence = planningZones.find((item) => item.channel === channel.name);
        const max = Math.max(
          100,
          Math.round(baseline * 3),
          Math.round((evidence?.safeBudgetCeiling ?? 0) * 1.6),
          Math.round(value * 1.1),
        );
        const delta = baseline > 0 ? ((value - baseline) / baseline) * 100 : 0;
        const inputId = `budget-${channel.name.toLowerCase().replaceAll(" ", "-")}`;
        return (
          <div key={channel.name}>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: channel.color ?? "var(--color-primary)" }}
                />
                <Label htmlFor={inputId} className="min-w-0 break-words font-medium">
                  {channel.name}
                </Label>
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
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Slider
                aria-label={`${channel.name} planned budget`}
                value={[value]}
                min={0}
                max={max}
                step={Math.max(100, Math.round(max / 200))}
                onValueChange={(next) => onChange(channel.name, next[0])}
                className="min-w-0 flex-1"
              />
              <Input
                id={inputId}
                aria-label={`${channel.name} planned budget input`}
                type="number"
                value={value}
                onChange={(event) =>
                  onChange(channel.name, Math.max(0, Number(event.target.value)))
                }
                className="w-full sm:w-28"
              />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
              <span>
                Proj. rev:{" "}
                <span className="font-medium text-foreground">
                  {fmtCurrency(channel.projectedRevenue ?? 0)}
                </span>
              </span>
              <span>
                ROAS:{" "}
                <span className="font-medium text-foreground">
                  {fmtRoas(channel.projectedRoas ?? 0)}
                </span>
              </span>
              {evidence && (
                <span>
                  Safe ceiling:{" "}
                  <span className="font-medium text-foreground">
                    {fmtCurrency(evidence.safeBudgetCeiling)}
                  </span>
                </span>
              )}
            </div>
            {evidence && (
              <details className="mt-2 rounded-md border border-border/50 bg-background/40 px-3 py-2 text-xs">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-2 font-medium">
                  <span>Why this planning zone?</span>
                  <Badge variant="outline" className={zoneBadgeClass(evidence.zone)}>
                    {zoneLabel(evidence.zone)}
                  </Badge>
                </summary>
                <p className="mt-2 text-muted-foreground">{evidence.reason}</p>
                <p className="mt-1 text-muted-foreground">
                  {evidence.comparableWindowCount} comparable windows; historical p90{" "}
                  {fmtCurrency(evidence.historicalP90)}, maximum{" "}
                  {fmtCurrency(evidence.historicalMaximum)}.
                </p>
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function zoneLabel(zone: PlanningZone): string {
  if (zone === "HIGH_EXTRAPOLATION") return "High extrapolation";
  return zone.toLowerCase().replace(/^./, (value) => value.toUpperCase());
}

export function zoneBadgeClass(zone: PlanningZone): string {
  if (zone === "SUPPORTED") return "border-success/50 text-success";
  if (zone === "CAUTION") return "border-warning/50 text-warning";
  return "border-destructive/50 text-destructive";
}
