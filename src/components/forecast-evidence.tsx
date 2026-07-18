import { AlertTriangle, CheckCircle2, GitCompareArrows, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { MODEL_EVIDENCE } from "@/lib/model-validation.generated";
import { fmtCurrency, fmtRoas } from "@/lib/format";
import type { DataReadinessScore } from "@/lib/types";

export interface ChannelForecastComparison {
  channel: string;
  historicalRevenue: number;
  expectedRevenue: number;
  lowerRevenue: number;
  upperRevenue: number;
  historicalRoas: number | null;
  expectedRoas: number | null;
}

export interface ConfidenceInputs {
  readiness: DataReadinessScore | null;
  historyDays: number | null;
  freshnessDays: number | null;
  missingValueRatePct: number | null;
  modelPath: string;
  intervalWidthPct: number;
  sampleCount: number;
  budgetZone: string | null;
}

export interface ForecastDriver {
  feature: string;
  label: string;
  direction: "positive" | "negative";
  impact: number;
  explanation: string;
}

export function ForecastEvidencePanel() {
  const evidence = MODEL_EVIDENCE;
  return (
    <Card
      data-testid="forecast-evidence-panel"
      className="mt-6 min-w-0 border-border/60 bg-gradient-card p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
            <h2 className="text-sm font-semibold">Forecast Evidence Panel</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Generated from committed rolling-origin backtests, calibration reports, the model
            artifact and evaluator verification. Values are not entered in the UI.
          </p>
        </div>
        <Badge variant="outline">
          {evidence.availability === "available" ? "Evidence verified" : "Evidence unavailable"}
        </Badge>
      </div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-border/50">
        <table className="w-full min-w-[720px] text-sm">
          <caption className="sr-only">
            Revenue and ROAS forecast error and interval coverage by horizon
          </caption>
          <thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left">Horizon</th>
              <th className="px-3 py-2 text-right">Revenue MAPE</th>
              <th className="px-3 py-2 text-right">ROAS MAPE</th>
              <th className="px-3 py-2 text-right">Revenue coverage</th>
              <th className="px-3 py-2 text-right">ROAS coverage</th>
              <th className="px-3 py-2 text-left">Selected path</th>
            </tr>
          </thead>
          <tbody>
            {evidence.horizons.map((row) => (
              <tr key={row.horizonDays} className="border-t border-border/50">
                <td className="px-3 py-2 font-medium">{row.horizonDays} days</td>
                <td className="px-3 py-2 text-right">{formatPct(row.revenueMapePct)}</td>
                <td className="px-3 py-2 text-right">{formatPct(row.roasMapePct)}</td>
                <td className="px-3 py-2 text-right">
                  {formatPct(row.revenueIntervalCoveragePct)}
                </td>
                <td className="px-3 py-2 text-right">{formatPct(row.roasIntervalCoveragePct)}</td>
                <td className="px-3 py-2">{friendlyModel(row.selectedMethod)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <EvidenceValue
          label="Model artifact"
          value={`${evidence.modelArtifact.type} v${evidence.modelArtifact.version ?? "?"}`}
        />
        <EvidenceValue
          label="Training-data period"
          value={
            evidence.modelArtifact.trainingStartDate && evidence.modelArtifact.trainingEndDate
              ? `${evidence.modelArtifact.trainingStartDate} to ${evidence.modelArtifact.trainingEndDate}`
              : "Evidence unavailable"
          }
        />
        <EvidenceValue
          label="Verification date"
          value={formatVerificationDate(evidence.runtime.verificationDate)}
        />
        <EvidenceValue
          label="Runtime status"
          value={
            evidence.runtime.deterministic === true && evidence.runtime.networkRequired === false
              ? "Deterministic · offline capable"
              : "Verification unavailable"
          }
        />
      </dl>

      <details className="mt-4 rounded-lg border border-border/50 bg-background/40 p-3 text-xs">
        <summary className="cursor-pointer font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          Evidence provenance and model-path policy
        </summary>
        <p className="mt-2 text-muted-foreground">{evidence.modelPathPolicy}</p>
        <p className="mt-2 break-words text-muted-foreground">
          Sources: {evidence.sources.join(", ")}
        </p>
      </details>
    </Card>
  );
}

export function WhyThisModelPanel() {
  return (
    <Card
      data-testid="why-this-model"
      className="mt-6 min-w-0 border-border/60 bg-gradient-card p-5"
    >
      <div className="flex items-center gap-2">
        <GitCompareArrows className="h-4 w-4 text-primary" aria-hidden="true" />
        <h2 className="text-sm font-semibold">Why this model?</h2>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Horizon-specific selections are generated from the repository&apos;s challenger validation.
      </p>
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {MODEL_EVIDENCE.horizons.map((row) => (
          <article key={row.horizonDays} className="rounded-lg border border-border/50 p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-semibold">{row.horizonDays}-day horizon</h3>
              <Badge variant="outline">{row.folds ?? 0} folds</Badge>
            </div>
            <dl className="mt-3 space-y-2 text-xs">
              <EvidenceValue label="Selected" value={friendlyModel(row.selectedMethod)} compact />
              <EvidenceValue
                label="Challenger"
                value={`${friendlyModel(row.challengerMethod)} (${formatPct(row.challengerRevenueMapePct)} revenue MAPE)`}
                compact
              />
              <EvidenceValue label="Selection reason" value={row.selectionReason} compact />
              <EvidenceValue label="Validation result" value={row.validationResult} compact />
              <EvidenceValue label="Major limitation" value={row.majorLimitation} compact />
            </dl>
          </article>
        ))}
      </div>
    </Card>
  );
}

export function HistoricalForecastComparison({
  horizon,
  historicalRevenue,
  expectedRevenue,
  lowerRevenue,
  upperRevenue,
  historicalRoas,
  expectedRoas,
  channels,
  partialError,
}: {
  horizon: number;
  historicalRevenue: number;
  expectedRevenue: number;
  lowerRevenue: number;
  upperRevenue: number;
  historicalRoas: number | null;
  expectedRoas: number | null;
  channels: ChannelForecastComparison[];
  partialError?: string | null;
}) {
  const changePct =
    historicalRevenue > 0
      ? ((expectedRevenue - historicalRevenue) / historicalRevenue) * 100
      : null;
  return (
    <Card
      data-testid="historical-forecast-comparison"
      className="mt-6 min-w-0 border-border/60 bg-gradient-card p-5"
    >
      <h2 className="text-sm font-semibold">Historical vs Forecast</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        The previous comparable {horizon}-day period is compared with the selected forecast and its
        planning range.
      </p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <EvidenceValue label="Previous revenue" value={fmtCurrency(historicalRevenue)} />
        <EvidenceValue label="Expected future revenue" value={fmtCurrency(expectedRevenue)} />
        <EvidenceValue
          label="Expected range"
          value={`${fmtCurrency(lowerRevenue)} – ${fmtCurrency(upperRevenue)}`}
        />
        <EvidenceValue
          label="Expected change"
          value={
            changePct === null
              ? "Not computable"
              : `${changePct >= 0 ? "+" : ""}${changePct.toFixed(1)}%`
          }
        />
        <EvidenceValue
          label="Historical ROAS"
          value={historicalRoas === null ? "Not computable" : fmtRoas(historicalRoas)}
        />
        <EvidenceValue
          label="Expected ROAS"
          value={expectedRoas === null ? "Not computable" : fmtRoas(expectedRoas)}
        />
      </dl>

      {channels.length > 0 ? (
        <div className="mt-4 overflow-x-auto rounded-lg border border-border/50">
          <table className="w-full min-w-[760px] text-sm">
            <caption className="sr-only">Channel-level historical and forecast comparison</caption>
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Channel</th>
                <th className="px-3 py-2 text-right">Historical revenue</th>
                <th className="px-3 py-2 text-right">Expected revenue</th>
                <th className="px-3 py-2 text-right">Range</th>
                <th className="px-3 py-2 text-right">Historical ROAS</th>
                <th className="px-3 py-2 text-right">Expected ROAS</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((row) => (
                <tr key={row.channel} className="border-t border-border/50">
                  <td className="px-3 py-2 font-medium">{row.channel}</td>
                  <td className="px-3 py-2 text-right">{fmtCurrency(row.historicalRevenue)}</td>
                  <td className="px-3 py-2 text-right">{fmtCurrency(row.expectedRevenue)}</td>
                  <td className="px-3 py-2 text-right">
                    {fmtCurrency(row.lowerRevenue)} – {fmtCurrency(row.upperRevenue)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {row.historicalRoas === null ? "N/A" : fmtRoas(row.historicalRoas)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {row.expectedRoas === null ? "N/A" : fmtRoas(row.expectedRoas)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-4 rounded-lg border border-border/50 bg-muted/30 p-3 text-xs text-muted-foreground">
          Channel forecasts are loading or unavailable. Next step: retry the forecast or select an
          individual channel above.
        </p>
      )}
      {partialError && (
        <p className="mt-3 flex gap-2 text-xs text-warning" role="status">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          {partialError} Next step: retry the forecast; available channels remain displayed.
        </p>
      )}
    </Card>
  );
}

export function ForecastConfidencePanel({ inputs }: { inputs: ConfidenceInputs }) {
  const positives: string[] = [];
  const reductions: string[] = [];
  if ((inputs.readiness?.score ?? 0) >= 75)
    positives.push(`Data Readiness is ${inputs.readiness?.score}/100.`);
  else
    reductions.push(
      inputs.readiness
        ? `Data Readiness is ${inputs.readiness.score}/100.`
        : "Data Readiness is unavailable.",
    );
  if ((inputs.historyDays ?? 0) >= 180)
    positives.push(`${inputs.historyDays} days of history support seasonality checks.`);
  else reductions.push(`${inputs.historyDays ?? 0} days of history limit long-horizon validation.`);
  if ((inputs.freshnessDays ?? Infinity) <= 7)
    positives.push(`Data is fresh within ${inputs.freshnessDays} days.`);
  else reductions.push(`Latest data is ${inputs.freshnessDays ?? "unknown"} days old.`);
  if ((inputs.missingValueRatePct ?? Infinity) <= 1)
    positives.push(`Missing-value rate is ${inputs.missingValueRatePct ?? 0}%.`);
  else reductions.push(`Missing-value rate is ${inputs.missingValueRatePct ?? "unknown"}%.`);
  if (inputs.intervalWidthPct <= 25)
    positives.push(
      `The revenue interval width is ${inputs.intervalWidthPct.toFixed(1)}% of expected revenue.`,
    );
  else
    reductions.push(
      `The revenue interval is wide at ${inputs.intervalWidthPct.toFixed(1)}% of expected revenue.`,
    );
  if (inputs.sampleCount >= 180)
    positives.push(`${inputs.sampleCount} usable rows support this view.`);
  else reductions.push(`Only ${inputs.sampleCount} usable rows support this view.`);
  if (!inputs.budgetZone || inputs.budgetZone === "SUPPORTED")
    positives.push("No unsupported budget extrapolation is active for this forecast.");
  else
    reductions.push(
      `The current planning snapshot is in the ${inputs.budgetZone.replaceAll("_", " ").toLowerCase()} zone.`,
    );

  return (
    <Card
      data-testid="forecast-confidence-explanation"
      className="mt-6 min-w-0 border-border/60 bg-gradient-card p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Forecast Confidence explanation</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Confidence explains evidence quality; it does not alter forecast values.
          </p>
        </div>
        <Badge variant="outline">Model path: {friendlyModel(inputs.modelPath)}</Badge>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <FactorList title="Positive confidence factors" items={positives} positive />
        <FactorList title="Confidence reductions" items={reductions} />
      </div>
    </Card>
  );
}

export function ForecastContributionWaterfall({ drivers }: { drivers: ForecastDriver[] }) {
  const supported = drivers
    .filter((driver) => Number.isFinite(driver.impact) && driver.impact !== 0)
    .slice(0, 8);
  if (!supported.length) return null;
  const maxImpact = Math.max(...supported.map((driver) => Math.abs(driver.impact)), 1);
  return (
    <Card
      data-testid="forecast-contribution-waterfall"
      className="mt-6 min-w-0 border-border/60 bg-gradient-card p-5"
    >
      <h2 className="text-sm font-semibold">Forecast-contribution waterfall</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Relative local model effects returned by the current explainability calculation. These are
        diagnostic effects, not an additive revenue reconciliation.
      </p>
      <div
        className="mt-4 space-y-3"
        role="img"
        aria-label="Relative positive and negative local forecast driver effects"
      >
        {supported.map((driver) => (
          <div
            key={`${driver.feature}-${driver.direction}`}
            className="grid grid-cols-[minmax(7rem,12rem)_1fr_auto] items-center gap-3 text-xs"
          >
            <span className="truncate font-medium" title={driver.label}>
              {driver.label}
            </span>
            <div className="relative h-6 rounded bg-muted/50">
              <div className="absolute left-1/2 top-0 h-full w-px bg-border" />
              <div
                className={
                  driver.direction === "positive"
                    ? "absolute left-1/2 h-full rounded-r bg-success/70"
                    : "absolute right-1/2 h-full rounded-l bg-destructive/70"
                }
                style={{ width: `${Math.max(2, (Math.abs(driver.impact) / maxImpact) * 50)}%` }}
                title={driver.explanation}
              />
            </div>
            <span className="tabular-nums text-muted-foreground">
              {driver.direction === "positive" ? "+" : "−"}
              {Math.abs(driver.impact).toFixed(3)}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function FactorList({
  title,
  items,
  positive = false,
}: {
  title: string;
  items: string[];
  positive?: boolean;
}) {
  return (
    <section className="rounded-lg border border-border/50 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      {items.length ? (
        <ul className="mt-3 space-y-2 text-sm">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              {positive ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
              ) : (
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                  aria-hidden="true"
                />
              )}
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">No factors in this category.</p>
      )}
    </section>
  );
}

function EvidenceValue({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <div
      className={
        compact ? "grid gap-0.5" : "rounded-lg border border-border/50 bg-background/40 p-3"
      }
    >
      <dt className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className={compact ? "break-words text-xs" : "mt-1 break-words text-sm font-semibold"}>
        {value}
      </dd>
    </div>
  );
}

function formatPct(value: number | null) {
  return value === null ? "N/A" : `${value.toFixed(2)}%`;
}

function friendlyModel(value: string) {
  if (value === "trained_model") return "Trained model";
  if (value === "trained_model_baseline_anchored") return "Baseline-anchored trained model";
  if (value === "safe_baseline_fallback") return "Safe baseline challenger";
  return value.replaceAll("_", " ");
}

function formatVerificationDate(value: string | null) {
  if (!value) return "Evidence unavailable";
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toISOString().slice(0, 10) : value;
}
