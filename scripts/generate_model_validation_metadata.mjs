import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const summaryPath = join(root, "reports", "backtest_summary.md");
const outputPath = join(root, "src", "lib", "model-validation.generated.ts");
const summary = readFileSync(summaryPath, "utf8");

const match = summary.match(
  /maximum representative\s+revenue delta of ([\d.]+)% and ROAS delta of\s+([\d.]+)%[\s\S]+?paths may differ up to ([\d.]+)%/i,
);

if (!match) {
  throw new Error("Could not parse model-path confidence values from reports/backtest_summary.md");
}

const [, revenueDelta, roasDelta, badgePct] = match;
const label = `Confidence: live/offline paths may differ up to ${Number(badgePct).toFixed(0)}%`;

const content = `export const MODEL_PATH_CONFIDENCE = {
  source: "reports/backtest_summary.md",
  maxRevenueDeltaPct: ${Number(revenueDelta)},
  maxRoasDeltaPct: ${Number(roasDelta)},
  badgePct: ${Number(badgePct)},
  label: ${JSON.stringify(label)},
} as const;
`;

writeFileSync(outputPath, content, "utf8");
console.log(`Generated ${outputPath} from ${summaryPath}`);
