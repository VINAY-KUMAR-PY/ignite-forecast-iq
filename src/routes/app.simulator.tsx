import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, DollarSign, Target, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { Card } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useData } from "@/lib/data-store";
import { fmtCompact, fmtCurrency, fmtPct, fmtRoas } from "@/lib/format";
import { KpiCard } from "@/components/kpi-card";

export const Route = createFileRoute("/app/simulator")({
  head: () => ({ meta: [{ title: "Budget simulator · ForecastIQ" }] }),
  component: SimulatorPage,
});

const CHANNELS = ["Google Ads", "Meta Ads", "Microsoft Ads"] as const;

function SimulatorPage() {
  const { rows } = useData();

  const baselines = useMemo(() => {
    if (!rows.length) return null;
    // Last 30 days averages per channel
    const dates = [...new Set(rows.map((r) => r.date))].sort();
    const lastN = new Set(dates.slice(-30));
    const recent = rows.filter((r) => lastN.has(r.date));
    const out: Record<string, { dailySpend: number; roas: number; revenue: number; spend: number }> = {};
    for (const ch of CHANNELS) {
      const chRows = recent.filter((r) => r.channel === ch);
      const spend = chRows.reduce((s, r) => s + r.spend, 0);
      const revenue = chRows.reduce((s, r) => s + r.revenue, 0);
      out[ch] = {
        dailySpend: spend / 30,
        spend,
        revenue,
        roas: spend > 0 ? revenue / spend : 0,
      };
    }
    return out;
  }, [rows]);

  const [budgets, setBudgets] = useState<Record<string, number>>({});

  if (!rows.length || !baselines) return (<><PageHeader title="Budget simulator" /><EmptyState /></>);

  const current = (ch: string) => budgets[ch] ?? Math.round(baselines[ch].dailySpend * 30);

  // Diminishing returns: revenue = baselineRevenue * (newSpend/baselineSpend)^0.85
  function project(ch: string) {
    const b = baselines[ch];
    const newSpend = current(ch);
    const baseSpend = b.dailySpend * 30 || 1;
    const ratio = newSpend / baseSpend;
    const efficiency = Math.pow(ratio, 0.85) / Math.max(ratio, 0.0001); // ratio^-0.15
    const projectedRevenue = b.revenue * Math.pow(ratio, 0.85);
    const projectedRoas = b.roas * efficiency;
    return { newSpend, projectedRevenue, projectedRoas, baseRevenue: b.revenue, baseSpend, baseRoas: b.roas };
  }

  const projections = CHANNELS.map((ch) => ({ ch, ...project(ch) }));
  const totalNewSpend = projections.reduce((s, p) => s + p.newSpend, 0);
  const totalProjRev = projections.reduce((s, p) => s + p.projectedRevenue, 0);
  const totalBaseRev = projections.reduce((s, p) => s + p.baseRevenue, 0);
  const totalBaseSpend = projections.reduce((s, p) => s + p.baseSpend, 0);
  const projRoas = totalNewSpend > 0 ? totalProjRev / totalNewSpend : 0;
  const baseRoas = totalBaseSpend > 0 ? totalBaseRev / totalBaseSpend : 0;
  const revChangePct = totalBaseRev > 0 ? ((totalProjRev - totalBaseRev) / totalBaseRev) * 100 : 0;
  const roasChangePct = baseRoas > 0 ? ((projRoas - baseRoas) / baseRoas) * 100 : 0;

  const chartData = projections.map((p) => ({
    name: p.ch,
    "Baseline revenue": Math.round(p.baseRevenue),
    "Projected revenue": Math.round(p.projectedRevenue),
  }));

  return (
    <>
      <PageHeader
        title="Budget simulator"
        description="Adjust 30-day budgets across channels. Revenue & ROAS recalculate in real time."
      />

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="bg-gradient-card border-border/60 p-6 lg:col-span-2">
          <h3 className="text-sm font-semibold">30-day channel budgets</h3>
          <p className="text-xs text-muted-foreground">Baseline = recent 30-day spend</p>
          <div className="mt-6 space-y-6">
            {CHANNELS.map((ch) => {
              const b = baselines[ch];
              const baseTotal = Math.max(1, Math.round(b.dailySpend * 30));
              const max = Math.round(baseTotal * 3);
              const v = current(ch);
              return (
                <div key={ch}>
                  <div className="flex items-center justify-between text-sm">
                    <Label className="font-medium">{ch}</Label>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">baseline {fmtCurrency(baseTotal)}</span>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-3">
                    <Slider
                      value={[v]}
                      min={0}
                      max={max}
                      step={Math.max(100, Math.round(max / 200))}
                      onValueChange={(val) => setBudgets((s) => ({ ...s, [ch]: val[0] }))}
                      className="flex-1"
                    />
                    <Input
                      type="number"
                      value={v}
                      onChange={(e) => setBudgets((s) => ({ ...s, [ch]: Math.max(0, Number(e.target.value)) }))}
                      className="w-28"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <div className="space-y-4 lg:col-span-3">
          <div className="grid gap-4 sm:grid-cols-2">
            <KpiCard label="Projected revenue" value={fmtCurrency(totalProjRev)} delta={revChangePct} icon={DollarSign} hint="vs baseline" />
            <KpiCard label="Projected ROAS" value={fmtRoas(projRoas)} delta={roasChangePct} icon={Target} hint="vs baseline" />
            <KpiCard label="Total spend" value={fmtCurrency(totalNewSpend)} icon={Activity} hint={`baseline ${fmtCurrency(totalBaseSpend)}`} />
            <KpiCard label="Revenue lift" value={`${revChangePct >= 0 ? "+" : ""}${fmtPct(revChangePct / 100)}`} icon={TrendingUp} hint={fmtCurrency(totalProjRev - totalBaseRev)} />
          </div>

          <Card className="bg-gradient-card border-border/60 p-5">
            <h3 className="mb-3 text-sm font-semibold">Budget impact by channel</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData} margin={{ left: -10, right: 8, top: 8 }}>
                <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke="var(--color-muted-foreground)" fontSize={11} />
                <YAxis stroke="var(--color-muted-foreground)" fontSize={11} tickFormatter={(v) => fmtCompact(v as number)} />
                <Tooltip content={<TT formatter={fmtCurrency} />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Baseline revenue" fill="var(--color-chart-2)" radius={[6, 6, 0, 0]} />
                <Bar dataKey="Projected revenue" fill="var(--color-chart-1)" radius={[6, 6, 0, 0]}>
                  {chartData.map((_, i) => <Cell key={i} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card className="bg-gradient-card border-border/60 p-5">
            <h3 className="mb-3 text-sm font-semibold">Channel breakdown</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 text-left">Channel</th>
                    <th className="px-2 py-2 text-right">Baseline spend</th>
                    <th className="px-2 py-2 text-right">New spend</th>
                    <th className="px-2 py-2 text-right">Proj. revenue</th>
                    <th className="px-2 py-2 text-right">Proj. ROAS</th>
                  </tr>
                </thead>
                <tbody>
                  {projections.map((p) => (
                    <tr key={p.ch} className="border-t border-border/40">
                      <td className="px-2 py-2 font-medium">{p.ch}</td>
                      <td className="px-2 py-2 text-right text-muted-foreground">{fmtCurrency(p.baseSpend)}</td>
                      <td className="px-2 py-2 text-right">{fmtCurrency(p.newSpend)}</td>
                      <td className="px-2 py-2 text-right">{fmtCurrency(p.projectedRevenue)}</td>
                      <td className="px-2 py-2 text-right">{fmtRoas(p.projectedRoas)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function TT({ active, payload, label, formatter }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-popover/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <div className="font-medium">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="mt-1 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.dataKey}:</span>
          <span className="font-medium">{formatter ? formatter(p.value) : p.value}</span>
        </div>
      ))}
    </div>
  );
}
