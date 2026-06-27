import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
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
}: {
  channels: BudgetSliderChannel[];
  budgets: Record<string, number>;
  onChange: (channel: string, value: number) => void;
}) {
  return (
    <div className="space-y-6">
      {channels.map((channel) => {
        const baseline = Math.max(1, Math.round(channel.baselineTotal));
        const value = budgets[channel.name] ?? baseline;
        const max = Math.round(baseline * 3);
        const delta = baseline > 0 ? ((value - baseline) / baseline) * 100 : 0;
        return (
          <div key={channel.name}>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: channel.color ?? "var(--color-primary)" }}
                />
                <Label className="min-w-0 break-words font-medium">{channel.name}</Label>
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
                value={[value]}
                min={0}
                max={max}
                step={Math.max(100, Math.round(max / 200))}
                onValueChange={(next) => onChange(channel.name, next[0])}
                className="min-w-0 flex-1"
              />
              <Input
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
            </div>
          </div>
        );
      })}
    </div>
  );
}
