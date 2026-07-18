import type { ForecastSnapshot, PlanningSnapshot } from "./data-store";
import type { InsightsResponse } from "./backend-api";
import type { DataReadinessScore } from "./types";
import { MODEL_EVIDENCE } from "./model-validation.generated";

export interface EvidenceBundleInput {
  executiveReport: Record<string, unknown>;
  insights: InsightsResponse;
  forecast: ForecastSnapshot | null;
  planning: PlanningSnapshot | null;
  dataReadiness: DataReadinessScore | null;
}

export function buildEvidenceBundle(input: EvidenceBundleInput) {
  return {
    format: "forecastiq-evidence-bundle",
    version: 1,
    generatedAt: new Date().toISOString(),
    contents: {
      executiveReport: {
        summary: input.executiveReport,
        narrative: input.insights.executiveSummary,
        actions: input.insights.actionPlan,
      },
      predictionsCsv: buildPredictionsCsv(input.forecast),
      scenarioComparison: input.planning
        ? {
            horizon: input.planning.horizon,
            allocationMode: input.planning.allocationMode,
            currentBudgets: input.planning.budgets,
            scenarios: input.planning.decisionSupport.scenarios,
            optimizer: input.planning.decisionSupport.optimizer,
            planningZones: input.planning.decisionSupport.planningZones,
          }
        : {
            status: "unavailable",
            nextStep: "Run the Budget Simulator to add scenario and extrapolation evidence.",
          },
      dataReadinessReport: input.dataReadiness ?? {
        status: "unavailable",
        nextStep: "Validate data on the Data Upload page.",
      },
      modelEvidence: MODEL_EVIDENCE,
      causalEvidence: input.insights.causalHypotheses ?? [],
      limitations: input.insights.provenance?.limitations ?? [
        "Observational evidence is not randomized incrementality proof.",
        "Forecast ranges are planning bounds, not guarantees.",
      ],
      provenanceConfiguration: {
        insightProvenance: input.insights.provenance ?? null,
        forecastSelection: input.forecast
          ? {
              horizon: input.forecast.horizon,
              level: input.forecast.level,
              value: input.forecast.value ?? null,
              modelType: input.forecast.response.summary.modelType,
            }
          : null,
        deterministicOfflineVerified:
          MODEL_EVIDENCE.runtime.deterministic === true &&
          MODEL_EVIDENCE.runtime.networkRequired === false,
        evidenceSources: MODEL_EVIDENCE.sources,
      },
    },
  };
}

export function downloadEvidenceBundle(input: EvidenceBundleInput) {
  const bundle = buildEvidenceBundle(input);
  const blob = new Blob([`${JSON.stringify(bundle, null, 2)}\n`], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `forecastiq-evidence-bundle-${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function buildPredictionsCsv(forecast: ForecastSnapshot | null) {
  if (!forecast) {
    return "status,next_step\nunavailable,Run the Forecasting page to add selected-view predictions.\n";
  }
  const revenue = forecast.response.revenue.filter((point) => !point.historical);
  const roasByDate = new Map(
    forecast.response.roas.filter((point) => !point.historical).map((point) => [point.date, point]),
  );
  const header = [
    "date",
    "expected_revenue",
    "lower_revenue",
    "upper_revenue",
    "expected_roas",
    "lower_roas",
    "upper_roas",
    "horizon_days",
    "level",
    "value",
    "model_type",
  ];
  const lines = revenue.map((point) => {
    const roas = roasByDate.get(point.date);
    return [
      point.date,
      point.value,
      point.lower,
      point.upper,
      roas?.value ?? "",
      roas?.lower ?? "",
      roas?.upper ?? "",
      forecast.horizon,
      forecast.level,
      forecast.value ?? "",
      forecast.response.summary.modelType,
    ]
      .map(csvCell)
      .join(",");
  });
  return `${header.join(",")}\n${lines.join("\n")}\n`;
}

function csvCell(value: unknown) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}
