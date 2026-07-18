import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { format } from "prettier";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const outputPath = join(root, "src", "lib", "model-validation.generated.ts");
const jsonOutputPath = join(root, "reports", "frontend_evidence.generated.json");
const sourcePaths = {
  backtest: join(root, "reports", "backtest_report.json"),
  calibration: join(root, "reports", "interval_calibration_report.json"),
  verification: join(root, "reports", "verification_summary.json"),
  requirements: join(root, "requirements.txt"),
  predictions: join(root, "output", "predictions.csv"),
  trainingData: join(root, "data", "sample_campaigns.csv"),
};

function sourceName(path) {
  return relative(root, path).replaceAll("\\", "/");
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function readCsv(path) {
  const [headerLine, ...lines] = readFileSync(path, "utf8").trim().split(/\r?\n/);
  const headers = headerLine.split(",");
  return lines
    .filter(Boolean)
    .map((line) =>
      Object.fromEntries(line.split(",").map((value, index) => [headers[index], value])),
    );
}

function finiteNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function buildEvidence() {
  const missingSources = Object.values(sourcePaths).filter((path) => !existsSync(path));
  if (missingSources.length > 0) {
    throw new Error(`Missing evidence sources: ${missingSources.map(sourceName).join(", ")}`);
  }

  const backtest = readJson(sourcePaths.backtest);
  const calibration = readJson(sourcePaths.calibration);
  const verification = readJson(sourcePaths.verification);
  const predictions = readCsv(sourcePaths.predictions);
  const trainingData = readCsv(sourcePaths.trainingData);
  const requirements = readFileSync(sourcePaths.requirements, "utf8");
  const sklearnMatch = requirements.match(/^scikit-learn==([^\s#]+)$/m);
  const walkForwardByHorizon = new Map(
    (calibration.latest_walk_forward_backtest ?? []).map((row) => [Number(row.horizon_days), row]),
  );

  const horizons = (backtest.horizon_planning_selection ?? []).map((selection) => {
    const horizonDays = Number(selection.horizon_days);
    const performance = walkForwardByHorizon.get(horizonDays) ?? {};
    const perHorizon = (backtest.per_horizon_performance ?? []).find(
      (row) => Number(row.horizon_days) === horizonDays,
    );
    const selectedMethod = selection.selected_method;
    const challengerMethod =
      selectedMethod === "trained_model" ? "safe_baseline_fallback" : "trained_model";
    const trainedRevenueMapePct = finiteNumber(perHorizon?.trained_model_metrics?.mape);
    const baselineRevenueMapePct = finiteNumber(perHorizon?.safe_baseline_metrics?.mape);
    return {
      horizonDays,
      selectedMethod,
      challengerMethod,
      selectionReason: selection.selection_reason,
      validationResult:
        perHorizon?.model_performance_evidence?.interpretation ??
        "No comparative validation interpretation was generated.",
      challengerRevenueMapePct:
        challengerMethod === "trained_model" ? trainedRevenueMapePct : baselineRevenueMapePct,
      majorLimitation:
        Number(perHorizon?.fold_count ?? 0) < 3
          ? `Only ${perHorizon?.fold_count ?? 0} rolling-origin folds were available at this horizon.`
          : `Validation covers ${perHorizon?.segments_evaluated ?? 0} segment-fold observations; performance on unseen regimes can still differ.`,
      revenueMapePct: finiteNumber(performance.revenue_mape ?? selection.selected_forecast_mape),
      roasMapePct: finiteNumber(performance.roas_mape),
      revenueIntervalCoveragePct: finiteNumber(
        performance.revenue_interval_coverage ?? selection.interval_coverage,
      ),
      roasIntervalCoveragePct: finiteNumber(
        perHorizon?.trained_model_metrics?.roas_interval_coverage,
      ),
      meanRevenueIntervalWidthPct: finiteNumber(
        performance.mean_interval_width_pct ?? selection.mean_interval_width_pct,
      ),
      folds: finiteNumber(performance.fold_count ?? perHorizon?.fold_count),
      segmentsEvaluated: finiteNumber(
        performance.segments_evaluated ?? perHorizon?.segments_evaluated,
      ),
    };
  });

  if (horizons.length !== 3 || horizons.some((row) => ![30, 60, 90].includes(row.horizonDays))) {
    throw new Error("Canonical reports do not contain complete 30/60/90-day evidence");
  }

  const modelTypeCounts = Object.fromEntries(
    Object.entries(
      predictions.reduce((counts, row) => {
        counts[row.model_type] = (counts[row.model_type] ?? 0) + 1;
        return counts;
      }, {}),
    ).sort(([left], [right]) => left.localeCompare(right)),
  );
  const overallByHorizon = predictions
    .filter((row) => row.level === "overall")
    .map((row) => ({
      horizonDays: finiteNumber(row.horizon_days),
      expectedRevenue: finiteNumber(row.expected_revenue),
      lowerRevenue: finiteNumber(row.lower_revenue),
      upperRevenue: finiteNumber(row.upper_revenue),
      expectedRoas: finiteNumber(row.expected_roas),
      lowerRoas: finiteNumber(row.lower_roas),
      upperRoas: finiteNumber(row.upper_roas),
      modelType: row.model_type,
      forecastConfidence: row.forecast_confidence,
    }))
    .sort((left, right) => left.horizonDays - right.horizonDays);

  const pathConsistency = backtest.model_path_consistency ?? {};
  const badgePct = finiteNumber(pathConsistency.badge_pct);
  const datedTrainingRows = trainingData
    .filter((row) => Number.isFinite(Date.parse(row.date)))
    .sort((left, right) => Date.parse(left.date) - Date.parse(right.date));
  const trainingRowCount = finiteNumber(backtest.model?.training_rows);
  const artifactTrainingRows = datedTrainingRows.slice(
    0,
    trainingRowCount === null ? datedTrainingRows.length : trainingRowCount,
  );
  return {
    availability: "available",
    statusLabel: "Verified repository evidence",
    generatedAt: verification.generated_at ?? backtest.generated_at ?? calibration.generated_at,
    horizons,
    modelPathPolicy:
      "The committed evaluator uses the trained artifact at 30 days and baseline-anchored revenue planning at 60/90 days when rolling-origin evidence does not support a trained-model advantage.",
    modelPathConfidence: {
      maxRevenueDeltaPct: finiteNumber(pathConsistency.max_revenue_delta_pct),
      maxRoasDeltaPct: finiteNumber(pathConsistency.max_roas_delta_pct),
      badgePct,
      label:
        badgePct === null
          ? "Evidence unavailable"
          : `Confidence: live/offline paths may differ up to ${badgePct.toFixed(0)}%`,
    },
    backendVerification: {
      coverageGatePct: 92.05,
      measuredCoveragePct: finiteNumber(verification.coverage?.coverage_pct),
      passed: finiteNumber(verification.coverage?.passed),
      skipped: finiteNumber(verification.coverage?.skipped),
      environmentNote: verification.environment?.optional_test_behavior ?? "Evidence unavailable",
    },
    sampleOutput: {
      rowCount: predictions.length,
      modelTypeCounts,
      overallByHorizon,
    },
    modelArtifact: {
      type: backtest.model?.artifact_type ?? "Evidence unavailable",
      version: finiteNumber(backtest.model?.artifact_version),
      modelType: backtest.model?.model_type ?? "Evidence unavailable",
      scikitLearnVersion:
        sklearnMatch?.[1] ?? backtest.environment?.scikit_learn ?? "Evidence unavailable",
      trainingRows: trainingRowCount,
      trainingSamples: finiteNumber(backtest.model?.training_samples),
      trainingStartDate: artifactTrainingRows.at(0)?.date ?? null,
      trainingEndDate: artifactTrainingRows.at(-1)?.date ?? null,
    },
    runtime: {
      verificationDate:
        verification.generated_at ?? backtest.generated_at ?? calibration.generated_at ?? null,
      deterministic: verification.evaluator?.deterministic === true,
      networkRequired: verification.evaluator?.network_required === true,
      outputSha256: verification.evaluator?.sha256?.["predictions.csv"] ?? null,
    },
    sources: Object.values(sourcePaths).map(sourceName),
  };
}

function unavailableEvidence(error) {
  return {
    availability: "unavailable",
    statusLabel: "Evidence unavailable",
    generatedAt: null,
    horizons: [],
    modelPathPolicy: "Evidence unavailable",
    modelPathConfidence: {
      maxRevenueDeltaPct: null,
      maxRoasDeltaPct: null,
      badgePct: null,
      label: "Evidence unavailable",
    },
    backendVerification: {
      coverageGatePct: null,
      measuredCoveragePct: null,
      passed: null,
      skipped: null,
      environmentNote: "Evidence unavailable",
    },
    sampleOutput: { rowCount: null, modelTypeCounts: {}, overallByHorizon: [] },
    modelArtifact: {
      type: "Evidence unavailable",
      version: null,
      modelType: "Evidence unavailable",
      scikitLearnVersion: "Evidence unavailable",
      trainingRows: null,
      trainingSamples: null,
      trainingStartDate: null,
      trainingEndDate: null,
    },
    runtime: {
      verificationDate: null,
      deterministic: null,
      networkRequired: null,
      outputSha256: null,
    },
    sources: Object.values(sourcePaths).map(sourceName),
    error: error instanceof Error ? error.message : String(error),
  };
}

let evidence;
try {
  evidence = buildEvidence();
} catch (error) {
  evidence = unavailableEvidence(error);
  console.warn(`Generating explicit evidence fallback: ${evidence.error}`);
}

const content = `// Generated by scripts/generate_model_validation_metadata.mjs. Do not edit manually.
export type ModelEvidenceHorizon = {
  readonly horizonDays: number;
  readonly selectedMethod: string;
  readonly challengerMethod: string;
  readonly selectionReason: string;
  readonly validationResult: string;
  readonly challengerRevenueMapePct: number | null;
  readonly majorLimitation: string;
  readonly revenueMapePct: number | null;
  readonly roasMapePct: number | null;
  readonly revenueIntervalCoveragePct: number | null;
  readonly roasIntervalCoveragePct: number | null;
  readonly meanRevenueIntervalWidthPct: number | null;
  readonly folds: number | null;
  readonly segmentsEvaluated: number | null;
};

export type ModelEvidence = {
  readonly availability: "available" | "unavailable";
  readonly statusLabel: string;
  readonly generatedAt: string | null;
  readonly horizons: readonly ModelEvidenceHorizon[];
  readonly modelPathPolicy: string;
  readonly modelPathConfidence: {
    readonly maxRevenueDeltaPct: number | null;
    readonly maxRoasDeltaPct: number | null;
    readonly badgePct: number | null;
    readonly label: string;
  };
  readonly backendVerification: {
    readonly coverageGatePct: number | null;
    readonly measuredCoveragePct: number | null;
    readonly passed: number | null;
    readonly skipped: number | null;
    readonly environmentNote: string;
  };
  readonly sampleOutput: {
    readonly rowCount: number | null;
    readonly modelTypeCounts: Readonly<Record<string, number>>;
    readonly overallByHorizon: readonly {
      readonly horizonDays: number | null;
      readonly expectedRevenue: number | null;
      readonly lowerRevenue: number | null;
      readonly upperRevenue: number | null;
      readonly expectedRoas: number | null;
      readonly lowerRoas: number | null;
      readonly upperRoas: number | null;
      readonly modelType: string;
      readonly forecastConfidence: string;
    }[];
  };
  readonly modelArtifact: {
    readonly type: string;
    readonly version: number | null;
    readonly modelType: string;
    readonly scikitLearnVersion: string;
    readonly trainingRows: number | null;
    readonly trainingSamples: number | null;
    readonly trainingStartDate: string | null;
    readonly trainingEndDate: string | null;
  };
  readonly runtime: {
    readonly verificationDate: string | null;
    readonly deterministic: boolean | null;
    readonly networkRequired: boolean | null;
    readonly outputSha256: string | null;
  };
  readonly sources: readonly string[];
  readonly error?: string;
};

export const MODEL_EVIDENCE: ModelEvidence = ${JSON.stringify(evidence, null, 2)} as const;

export const MODEL_PATH_CONFIDENCE = MODEL_EVIDENCE.modelPathConfidence;
`;

writeFileSync(
  outputPath,
  await format(content, {
    parser: "typescript",
    printWidth: 100,
    semi: true,
    singleQuote: false,
    trailingComma: "all",
  }),
  "utf8",
);
writeFileSync(jsonOutputPath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
console.log(
  `Generated ${outputPath} and ${jsonOutputPath} from ${evidence.sources.join(", ")} (${evidence.availability})`,
);
