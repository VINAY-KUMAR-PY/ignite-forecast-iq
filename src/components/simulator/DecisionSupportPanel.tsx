import {
  AlertTriangle,
  ArrowRightLeft,
  Gauge,
  Lightbulb,
  Sparkles,
  Target,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  type BudgetOptimizerResult,
  type ChannelHealthScore,
  type DetectionItem,
  type WhatIfScenarioResult,
} from "@/lib/backend-api";
import { fmtCurrency, fmtRoas } from "@/lib/format";

type RiskLevel = "Low" | "Medium" | "High";

export function DecisionSupportPanel({
  optimizer,
  whatIf,
  riskAlerts,
  opportunityAlerts,
  channelHealth,
  currentRevenue,
  currentRoas,
  horizon,
  targetRevenueDraft,
  targetRoasDraft,
  onTargetRevenueChange,
  onTargetRoasChange,
  onApplyTargets,
}: {
  optimizer: BudgetOptimizerResult;
  whatIf: WhatIfScenarioResult[];
  riskAlerts: DetectionItem[];
  opportunityAlerts: DetectionItem[];
  channelHealth: ChannelHealthScore[];
  currentRevenue: number;
  currentRoas: number;
  horizon: 30 | 60 | 90;
  targetRevenueDraft: string;
  targetRoasDraft: string;
  onTargetRevenueChange: (value: string) => void;
  onTargetRoasChange: (value: string) => void;
  onApplyTargets: () => void;
}) {
  const brief = buildOptimizerBrief(
    optimizer,
    riskAlerts,
    channelHealth,
    currentRevenue,
    currentRoas,
  );
  const topOpportunity = opportunityAlerts[0];
  const topRisk = riskAlerts[0];
  const topRecommendation = optimizer.recommendations[0];

  return (
    <div data-testid="decision-support" className="mt-6 grid min-w-0 gap-4">
      <Card
        data-testid="ai-budget-optimizer"
        className="bg-gradient-card border-border/60 min-w-0 p-5"
      >
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold">Evidence-constrained budget optimizer</h3>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Set target revenue and ROAS, then compare recommended Google, Meta and Microsoft
              budgets.
            </p>
          </div>
          <div className="grid min-w-0 gap-2 sm:grid-cols-[140px_120px_auto]">
            <Input
              type="number"
              min={0}
              value={targetRevenueDraft}
              onChange={(event) => onTargetRevenueChange(event.target.value)}
              placeholder={`${Math.round(currentRevenue * 1.1)}`}
              aria-label="Target revenue"
            />
            <Input
              type="number"
              min={0}
              step="0.1"
              value={targetRoasDraft}
              onChange={(event) => onTargetRoasChange(event.target.value)}
              placeholder={`${Math.max(0, currentRoas * 1.05).toFixed(1)}`}
              aria-label="Target ROAS"
            />
            <Button type="button" variant="hero" onClick={onApplyTargets}>
              <Target className="mr-2 h-4 w-4" />
              Optimize
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <DecisionStat
            label="Recommended budget"
            value={fmtCurrency(optimizer.recommendedBudget)}
            hint={`current ${fmtCurrency(optimizer.currentBudget)}`}
          />
          <DecisionStat
            label="Expected revenue"
            value={fmtCurrency(optimizer.expectedRevenue)}
            hint={formatTargetGap(optimizer.targetGapRevenue, "revenue")}
          />
          <DecisionStat
            label="Expected ROAS"
            value={fmtRoas(optimizer.expectedRoas)}
            hint={formatTargetGap(optimizer.targetGapRoas, "roas")}
          />
          <DecisionStat
            label="Expected profit"
            value={fmtCurrency(optimizer.expectedProfit)}
            hint="revenue minus media spend"
          />
        </div>

        <div
          data-testid="optimizer-uncertainty-verdict"
          className="mt-4 rounded-lg border border-border/60 bg-background/50 p-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Uncertainty-aware verdict
              </div>
              <p className="mt-1 text-sm font-semibold">{optimizer.verdict}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {optimizer.uncertaintyCalculation}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className={optimizerOutcomeBadgeClass(optimizer.outcome)}>
                {optimizer.outcome.replaceAll("_", " ")}
              </Badge>
              <Badge
                variant="outline"
                className={
                  optimizer.meaningful
                    ? "border-success/50 text-success"
                    : "border-warning/50 text-warning"
                }
              >
                {optimizer.meaningful
                  ? "Meaningful vs uncertainty"
                  : "Not meaningful vs uncertainty"}
              </Badge>
            </div>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <DecisionStat
              label="Expected gain"
              value={formatMoneyDelta(optimizer.absoluteGain)}
              hint={`${optimizer.gainPct >= 0 ? "+" : ""}${optimizer.gainPct.toFixed(2)}% vs current plan`}
            />
            <DecisionStat
              label="Noise floor"
              value={fmtCurrency(optimizer.uncertaintyNoiseFloor)}
              hint="sum of baseline and optimized interval half-widths"
            />
            <DecisionStat
              label="Safe alternative"
              value={fmtCurrency(optimizer.maxSupportedTotalBudget)}
              hint="maximum combined historical p90 ceiling"
            />
          </div>
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer font-medium">Why this recommendation?</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
              {optimizer.constraintNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </details>
        </div>

        <div
          data-testid="optimizer-executive-brief"
          className="mt-4 min-w-0 rounded-lg border border-primary/20 bg-primary/5 p-4"
        >
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-wider text-primary">
                Optimizer recommendation
              </div>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{brief.explanation}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge
                variant="outline"
                className={optimizerConfidenceBadgeClass(brief.confidenceScore)}
              >
                {brief.confidenceScore}/100 confidence
              </Badge>
              <Badge variant="outline" className={optimizerRiskBadgeClass(brief.riskLevel)}>
                {brief.riskLevel} risk
              </Badge>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <DecisionStat label="Channel shift" value={brief.channelMove} hint="exact media move" />
            <DecisionStat
              label="Wasted spend reduction"
              value={brief.wastedSpend}
              hint="budget recycled"
            />
            <DecisionStat
              label="Revenue lift"
              value={formatMoneyDelta(brief.revenueLift)}
              hint="vs current plan"
            />
            <DecisionStat
              label="ROAS improvement"
              value={formatRoasDelta(brief.roasLift)}
              hint="expected lift"
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-4">
          <EvidenceCard
            title="Opportunity"
            value={topOpportunity?.message ?? "Keep the current plan under watch."}
            detail={topOpportunity?.recommendation ?? "No high-confidence upside alert is active."}
          />
          <EvidenceCard
            title="Risk"
            value={topRisk?.message ?? "No major risk alert is active."}
            detail={
              topRisk?.recommendation ?? "Continue monitoring interval width and channel health."
            }
          />
          <EvidenceCard
            title="Recommended Action"
            value={
              topRecommendation
                ? `${formatMoneyDelta(topRecommendation.deltaBudget)} ${topRecommendation.channel}`
                : "Hold budget steady"
            }
            detail={
              topRecommendation?.rationale ?? "Wait for stronger evidence before reallocating."
            }
          />
          <EvidenceCard
            title="Evidence and Confidence"
            value={optimizer.verdict}
            detail={`Projected gain ${formatMoneyDelta(optimizer.absoluteGain)} versus a ${fmtCurrency(
              optimizer.uncertaintyNoiseFloor,
            )} uncertainty noise floor.`}
          />
        </div>

        <div className="mt-4 min-w-0 rounded-lg border border-border/40 bg-background/40 p-4">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Recommended allocation
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Channel-level action plan for the next {horizon} days.
              </p>
            </div>
            <div className="min-w-0 text-left text-xs sm:text-right">
              <div className="font-medium text-success">
                {formatMoneyDelta(optimizer.expectedRevenue - currentRevenue)}
              </div>
              <div className="text-muted-foreground">
                Revenue lift, {formatRoasDelta(optimizer.expectedRoas - currentRoas)} ROAS
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {optimizer.recommendations.map((recommendation) => (
              <div
                key={recommendation.channel}
                className="min-w-0 rounded-md border border-border/40 bg-background/50 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0 break-words text-sm font-medium">
                    {recommendation.channel}
                  </div>
                  <span
                    className={`text-xs font-semibold ${deltaClass(recommendation.deltaBudget)}`}
                  >
                    {formatMoneyDelta(recommendation.deltaBudget)}
                  </span>
                </div>
                <div className="mt-2 break-words text-lg font-semibold">
                  {fmtCurrency(recommendation.recommendedBudget)}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Expected ROAS {fmtRoas(recommendation.expectedRoas)}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{recommendation.rationale}</p>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        <Card
          data-testid="what-if-engine"
          className="bg-gradient-card border-border/60 min-w-0 p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">What-if scenario engine</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-2 py-2 text-left">Scenario</th>
                  <th className="px-2 py-2 text-right">Revenue</th>
                  <th className="px-2 py-2 text-right">ROAS</th>
                  <th className="px-2 py-2 text-right">Profit</th>
                  <th className="px-2 py-2 text-right">Revenue impact</th>
                </tr>
              </thead>
              <tbody>
                {whatIf.slice(0, 7).map((scenario) => (
                  <ScenarioRow key={scenario.name} scenario={scenario} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          data-testid="channel-health"
          className="bg-gradient-card border-border/60 min-w-0 p-5"
        >
          <div className="mb-4 flex items-center gap-2">
            <Gauge className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">Channel health score</h3>
          </div>
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">
            Formula: projected ROAS plus revenue trend plus budget-share fit, minus efficiency risk
            penalties. 80+ is healthy, 60-79 needs watch, below 60 is critical.
          </p>
          <div className="space-y-4">
            {channelHealth.map((item) => (
              <HealthRow key={item.channel} item={item} />
            ))}
          </div>
        </Card>
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        <DetectionPanel
          title="Risk detection engine"
          icon={AlertTriangle}
          items={riskAlerts}
          testId="risk-detection"
        />
        <DetectionPanel
          title="Opportunity detection engine"
          icon={Lightbulb}
          items={opportunityAlerts}
          testId="opportunity-detection"
        />
      </div>
    </div>
  );
}

function buildOptimizerBrief(
  optimizer: BudgetOptimizerResult,
  risks: DetectionItem[],
  health: ChannelHealthScore[],
  currentRevenue: number,
  currentRoas: number,
) {
  const recommendations = optimizer.recommendations;
  const increase = [...recommendations].sort((a, b) => b.deltaBudget - a.deltaBudget)[0];
  const decrease = [...recommendations].sort((a, b) => a.deltaBudget - b.deltaBudget)[0];
  const hasShift = increase && decrease && increase.deltaBudget > 0 && decrease.deltaBudget < 0;
  const shift = hasShift
    ? Math.min(increase.deltaBudget, Math.abs(decrease.deltaBudget))
    : Math.max(0, increase?.deltaBudget ?? 0);
  const channelMove =
    hasShift && shift > 0
      ? `${fmtCurrency(shift)} ${decrease.channel} -> ${increase.channel}`
      : increase && shift > 0
        ? `Add ${fmtCurrency(shift)} to ${increase.channel}`
        : "Hold current channel mix";
  const revenueLift = optimizer.expectedRevenue - currentRevenue;
  const roasLift = optimizer.expectedRoas - currentRoas;
  const highRisks = risks.filter((item) => item.severity === "high").length;
  const mediumRisks = risks.filter((item) => item.severity === "medium").length;
  const averageHealth = health.length
    ? health.reduce((sum, item) => sum + item.score, 0) / health.length
    : 74;
  const confidenceScore = Math.round(
    clampNumber(
      averageHealth - highRisks * 8 - mediumRisks * 4 + Math.min(8, Math.max(0, roasLift) * 12),
      55,
      96,
    ),
  );
  const riskLevel: RiskLevel =
    highRisks > 0 ? "High" : mediumRisks > 0 || confidenceScore < 72 ? "Medium" : "Low";
  const explanation =
    hasShift && shift > 0
      ? `Recycle budget from ${decrease.channel} into ${increase.channel}. The plan protects blended ROAS while funding the highest-growth channel.`
      : increase
        ? `The safest next move is to fund ${increase.channel} while keeping the rest of the plan close to baseline.`
        : "The current plan is balanced; keep budgets steady and monitor marginal ROAS before scaling.";
  return {
    channelMove,
    wastedSpend: shift > 0 ? fmtCurrency(shift) : "No cut required",
    revenueLift,
    roasLift,
    confidenceScore,
    riskLevel,
    explanation,
  };
}

function DecisionStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/40 p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-lg font-semibold">{value}</div>
      <div className="mt-1 break-words text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}

function EvidenceCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/40 bg-background/50 p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      <div className="mt-1 break-words text-sm font-semibold">{value}</div>
      <p className="mt-2 break-words text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

function ScenarioRow({ scenario }: { scenario: WhatIfScenarioResult }) {
  return (
    <tr className="border-t border-border/40">
      <td className="px-2 py-2 font-medium">{scenario.name}</td>
      <td className="px-2 py-2 text-right">{fmtCurrency(scenario.projectedRevenue)}</td>
      <td className="px-2 py-2 text-right">{fmtRoas(scenario.projectedRoas)}</td>
      <td className="px-2 py-2 text-right">{fmtCurrency(scenario.projectedProfit)}</td>
      <td className={`px-2 py-2 text-right font-medium ${deltaClass(scenario.revenueDeltaPct)}`}>
        {formatPctDelta(scenario.revenueDeltaPct)}
      </td>
    </tr>
  );
}

function HealthRow({ item }: { item: ChannelHealthScore }) {
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words text-sm font-medium">{item.channel}</div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            Revenue share {item.revenueSharePct.toFixed(1)}% - Spend share{" "}
            {item.spendSharePct.toFixed(1)}%
          </div>
        </div>
        <Badge variant="outline" className={`shrink-0 ${healthBadgeClass(item.status)}`}>
          {item.score.toFixed(0)}/100 - {item.status}
        </Badge>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary"
          style={{ width: `${Math.min(100, Math.max(0, item.score))}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.drivers.map((driver) => (
          <span
            key={driver}
            className="rounded-full border border-border/40 bg-background/40 px-2 py-0.5 text-[10px] text-muted-foreground"
          >
            {driver}
          </span>
        ))}
      </div>
    </div>
  );
}

function DetectionPanel({
  title,
  icon: Icon,
  items,
  testId,
}: {
  title: string;
  icon: LucideIcon;
  items: DetectionItem[];
  testId: string;
}) {
  return (
    <Card data-testid={testId} className="bg-gradient-card border-border/60 min-w-0 p-5">
      <div className="mb-4 flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="space-y-3">
        {items.map((item, index) => (
          <div
            key={`${item.type}-${item.channel ?? index}`}
            className="rounded-lg border border-border/40 bg-background/40 p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0 break-words text-sm font-medium">
                {item.channel ?? item.type.replaceAll("_", " ")}
              </div>
              <Badge variant="outline" className={severityBadgeClass(item.severity)}>
                {item.severity} - {item.score.toFixed(0)}
              </Badge>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{item.message}</p>
            <p className="mt-2 text-xs">
              <span className="font-medium text-foreground">Action: </span>
              <span className="text-muted-foreground">{item.recommendation}</span>
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

function formatMoneyDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${fmtCurrency(value)}`;
}

function formatPctDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatRoasDelta(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}x`;
}

function formatTargetGap(value: number, type: "revenue" | "roas") {
  if (!value) return "target met or not set";
  if (value <= 0) return "target met";
  return type === "revenue" ? `${fmtCurrency(value)} gap` : `${value.toFixed(2)}x gap`;
}

function deltaClass(value: number) {
  if (value > 0) return "text-success";
  if (value < 0) return "text-destructive";
  return "text-muted-foreground";
}

function severityBadgeClass(severity: DetectionItem["severity"]) {
  if (severity === "high") return "border-destructive/30 bg-destructive/15 text-destructive";
  if (severity === "medium") return "border-warning/30 bg-warning/15 text-warning";
  return "border-border bg-muted text-muted-foreground";
}

function healthBadgeClass(status: ChannelHealthScore["status"]) {
  if (status === "healthy") return "border-success/30 bg-success/15 text-success";
  if (status === "watch") return "border-warning/30 bg-warning/15 text-warning";
  return "border-destructive/30 bg-destructive/15 text-destructive";
}

function optimizerConfidenceBadgeClass(score: number) {
  if (score >= 85) return "border-success/30 bg-success/15 text-success";
  if (score >= 70) return "border-primary/30 bg-primary/15 text-primary";
  return "border-warning/30 bg-warning/15 text-warning";
}

function optimizerRiskBadgeClass(level: RiskLevel) {
  if (level === "High") return "border-destructive/30 bg-destructive/15 text-destructive";
  if (level === "Medium") return "border-warning/30 bg-warning/15 text-warning";
  return "border-success/30 bg-success/15 text-success";
}

function optimizerOutcomeBadgeClass(outcome: BudgetOptimizerResult["outcome"]) {
  if (outcome === "IMPROVED_ABOVE_NOISE") {
    return "border-success/30 bg-success/15 text-success";
  }
  if (outcome === "IMPROVED_WITHIN_NOISE" || outcome === "NO_CHANGE") {
    return "border-warning/30 bg-warning/15 text-warning";
  }
  return "border-destructive/30 bg-destructive/15 text-destructive";
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
