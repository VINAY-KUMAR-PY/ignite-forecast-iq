import { useEffect } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Info,
  ListChecks,
  RefreshCw,
} from "lucide-react";
import { useData, type ReadinessStatus } from "@/lib/data-store";
import type { DataReadinessRating, DataReadinessScore } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type ReadinessContext = "upload" | "decision" | "forecast";

export function DataReadinessPanel({ context }: { context: ReadinessContext }) {
  const { rows, dataReadiness, readinessStatus, readinessError, ensureDataReadiness } = useData();

  useEffect(() => {
    if (rows.length && readinessStatus === "idle" && !dataReadiness) {
      void ensureDataReadiness();
    }
  }, [rows.length, readinessStatus, dataReadiness, ensureDataReadiness]);

  if (!rows.length && context !== "upload") return null;

  return (
    <DataReadinessScoreCard
      score={dataReadiness}
      status={readinessStatus}
      error={readinessError}
      context={context}
      onRetry={() => void ensureDataReadiness(true)}
    />
  );
}

export function DataReadinessScoreCard({
  score,
  status,
  error,
  context,
  onRetry,
}: {
  score: DataReadinessScore | null;
  status: ReadinessStatus;
  error?: string | null;
  context: ReadinessContext;
  onRetry?: () => void;
}) {
  const heading =
    context === "forecast" ? "Data quality and forecast confidence" : "Data Readiness Score";

  if (status === "loading" || (status === "idle" && !score)) {
    return (
      <Card
        data-testid="data-readiness-loading"
        className="mb-6 min-w-0 border-border/60 bg-gradient-card p-5"
        role="status"
        aria-live="polite"
      >
        <div className="flex items-center gap-3">
          <RefreshCw className="h-5 w-5 animate-spin text-primary" aria-hidden="true" />
          <div>
            <h2 className="text-sm font-semibold">Calculating Data Readiness Score</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Reusing schema, validation, coverage, duplicate, and anomaly evidence.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  if (!score) {
    return (
      <Card
        data-testid="data-readiness-fallback"
        className="mb-6 min-w-0 border-warning/40 bg-warning/5 p-5"
        role="status"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
            <div>
              <h2 className="text-sm font-semibold">Data Readiness Score unavailable</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Browser validation remains available, but ForecastIQ will not invent a score without
                backend validation evidence. {error || "Start the API and retry the assessment."}
              </p>
            </div>
          </div>
          {onRetry && (
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" /> Retry score
            </Button>
          )}
        </div>
      </Card>
    );
  }

  const compact = context !== "upload";
  return (
    <Card
      data-testid="data-readiness-score"
      className="mb-6 min-w-0 border-border/60 bg-gradient-card p-4 sm:p-5"
      aria-labelledby={`data-readiness-heading-${context}`}
    >
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <div
            className={`grid h-20 w-20 shrink-0 place-items-center rounded-2xl border text-center ${ratingClass(score.rating)}`}
            aria-label={`${score.score} out of 100, ${score.rating}`}
          >
            <div>
              <div data-testid="data-readiness-value" className="text-2xl font-bold leading-none">
                {score.score}
              </div>
              <div className="mt-1 text-[10px] font-semibold uppercase tracking-wider">of 100</div>
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <ClipboardCheck className="h-4 w-4 text-primary" aria-hidden="true" />
              <h2 id={`data-readiness-heading-${context}`} className="text-sm font-semibold">
                {heading}
              </h2>
              <span
                data-testid="data-readiness-rating"
                className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${ratingClass(score.rating)}`}
              >
                {score.rating}
              </span>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
              {score.confidenceExplanation}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Evidence evaluated as of {score.evaluatedAsOf}. This is a data-quality assessment, not
              a guarantee of model accuracy.
            </p>
          </div>
        </div>
        <div className="grid shrink-0 grid-cols-2 gap-2 text-center sm:grid-cols-4 lg:grid-cols-2">
          <Metric label="History" value={`${numberMetric(score, "historyDays")} days`} />
          <Metric label="Valid rows" value={numberMetric(score, "validRows").toLocaleString()} />
          <Metric label="Channels" value={String(numberMetric(score, "usableChannels"))} />
          <Metric
            label="Date consistency"
            value={`${numberMetric(score, "dateConsistencyPct").toFixed(0)}%`}
          />
        </div>
      </div>

      <div
        data-testid="data-readiness-components"
        className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        {score.components.map((component) => (
          <div
            key={component.key}
            className="min-w-0 rounded-lg border border-border/50 bg-background/45 p-3"
          >
            <div className="flex items-start justify-between gap-2 text-xs">
              <span className="font-medium">{component.label}</span>
              <span className="shrink-0 font-semibold">
                {component.score}/100
                <span className="sr-only">, weighted {component.weight} percent</span>
              </span>
            </div>
            <div
              className="mt-2 h-2 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label={`${component.label} score`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={component.score}
            >
              <div
                className="h-full rounded-full bg-primary transition-[width]"
                style={{ width: `${component.score}%` }}
              />
            </div>
            {(!compact || component.score < 75) && (
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {component.summary}
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <EvidenceList
          title="Positive evidence"
          icon={CheckCircle2}
          items={score.positiveEvidence}
          empty="No positive evidence is available yet."
          tone="positive"
        />
        <EvidenceList
          title="Warnings"
          icon={AlertTriangle}
          items={score.warnings}
          empty="No material data-quality warnings were detected."
          tone="warning"
        />
        <EvidenceList
          title="Recommended actions"
          icon={ListChecks}
          items={score.recommendedActions}
          empty="No corrective action is required before forecasting."
          tone="action"
        />
      </div>

      <details className="mt-5 rounded-lg border border-border/50 bg-background/35 p-3">
        <summary className="cursor-pointer rounded-sm text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background">
          How this score is calculated
        </summary>
        <div className="mt-3 space-y-3 text-xs leading-relaxed text-muted-foreground">
          <p>
            Each component is scored from 0 to 100 using deterministic validation evidence. The
            overall score is the rounded weighted sum; ratings are Excellent (90-100), Good (75-89),
            Usable with caution (60-74), or Needs attention (below 60).
          </p>
          <ul className="grid list-disc gap-x-8 gap-y-1 pl-5 sm:grid-cols-2">
            {score.components.map((component) => (
              <li key={component.key}>
                {component.label}: {component.weight}%
              </li>
            ))}
          </ul>
          <p className="flex gap-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            Historical coverage reaches full credit at 180 days. Freshness compares the latest valid
            date with the displayed evaluation date. Cross-source consistency is not penalized for a
            single source. Severe outliers come from ForecastIQ's existing anomaly detector.
          </p>
        </div>
      </details>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/50 bg-background/45 px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  );
}

function EvidenceList({
  title,
  icon: Icon,
  items,
  empty,
  tone,
}: {
  title: string;
  icon: typeof CheckCircle2;
  items: string[];
  empty: string;
  tone: "positive" | "warning" | "action";
}) {
  const toneClass =
    tone === "positive" ? "text-success" : tone === "warning" ? "text-warning" : "text-primary";
  return (
    <section className="rounded-lg border border-border/50 bg-background/45 p-4">
      <h3
        className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-wider ${toneClass}`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" /> {title}
      </h3>
      {items.length ? (
        <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span aria-hidden="true">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">{empty}</p>
      )}
    </section>
  );
}

function ratingClass(rating: DataReadinessRating) {
  if (rating === "Excellent") return "border-success/40 bg-success/10 text-success";
  if (rating === "Good") return "border-primary/40 bg-primary/10 text-primary";
  if (rating === "Usable with caution") return "border-warning/50 bg-warning/10 text-warning";
  return "border-destructive/40 bg-destructive/10 text-destructive";
}

function numberMetric(score: DataReadinessScore, key: string) {
  const value = score.metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
