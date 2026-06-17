import type { CampaignRow, ForecastPoint } from "./types";

/**
 * Forecasting engine — gradient boosted regression trees (XGBoost-style).
 *
 * Implements a from-scratch gradient boosting regressor (squared-error loss)
 * trained on engineered features:
 *   spend, clicks, impressions, conversions, day-of-week, month,
 *   lag(1/7/14) of target, rolling-mean(7/28) of target, lag(1/7) of spend.
 *
 * Two models are trained: one for daily revenue, one for daily ROAS.
 * Future exogenous features (spend/clicks/impressions/conversions) are
 * projected forward using a 28-day mean × weekly seasonality factor, then
 * fed recursively into the booster to roll the forecast out h steps.
 *
 * Confidence bands use the in-sample residual std-dev, widened by sqrt(h).
 */

// ---------------------------------------------------------------------------
// Aggregation & filtering
// ---------------------------------------------------------------------------

export interface DailyAgg {
  date: string;
  spend: number;
  clicks: number;
  impressions: number;
  conversions: number;
  revenue: number;
  roas: number;
}

export function aggregateDaily(rows: CampaignRow[]): DailyAgg[] {
  const map = new Map<string, Omit<DailyAgg, "date" | "roas">>();
  for (const r of rows) {
    const cur = map.get(r.date) ?? { spend: 0, clicks: 0, impressions: 0, conversions: 0, revenue: 0 };
    cur.spend += r.spend;
    cur.clicks += r.clicks;
    cur.impressions += r.impressions;
    cur.conversions += r.conversions;
    cur.revenue += r.revenue;
    map.set(r.date, cur);
  }
  return [...map.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([date, v]) => ({ date, ...v, roas: v.spend > 0 ? v.revenue / v.spend : 0 }));
}

export function filterRows(
  rows: CampaignRow[],
  filter: { level: "overall" | "channel" | "campaign_type" | "campaign"; value?: string },
): CampaignRow[] {
  if (filter.level === "overall" || !filter.value) return rows;
  const key =
    filter.level === "channel" ? "channel" : filter.level === "campaign_type" ? "campaign_type" : "campaign_name";
  return rows.filter((r) => r[key] === filter.value);
}

// ---------------------------------------------------------------------------
// Gradient Boosted Regression Trees (XGBoost-style, squared-error)
// ---------------------------------------------------------------------------

interface TreeNode {
  leaf?: number;
  feature?: number;
  threshold?: number;
  left?: TreeNode;
  right?: TreeNode;
}

interface GBRTModel {
  base: number;
  lr: number;
  trees: TreeNode[];
}

interface GBRTParams {
  nEstimators: number;
  maxDepth: number;
  learningRate: number;
  minSamplesSplit: number;
  subsample: number; // feature subsampling fraction (column sampling per tree)
}

const DEFAULT_PARAMS: GBRTParams = {
  nEstimators: 60,
  maxDepth: 4,
  learningRate: 0.08,
  minSamplesSplit: 4,
  subsample: 0.8,
};

// Seeded RNG for deterministic column subsampling
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildTree(
  X: number[][],
  y: number[],
  features: number[],
  depth: number,
  params: GBRTParams,
): TreeNode {
  const n = y.length;
  const mean = y.reduce((s, v) => s + v, 0) / Math.max(1, n);
  if (depth >= params.maxDepth || n < params.minSamplesSplit) return { leaf: mean };

  let bestGain = 0;
  let bestFeat = -1;
  let bestThr = 0;
  let bestLeft: number[] = [];
  let bestRight: number[] = [];

  const totalSum = y.reduce((s, v) => s + v, 0);
  const totalSqSum = y.reduce((s, v) => s + v * v, 0);
  const parentSSE = totalSqSum - (totalSum * totalSum) / n;

  for (const f of features) {
    // candidate thresholds: quantiles of feature column
    const vals = X.map((row) => row[f]).slice().sort((a, b) => a - b);
    const candidates: number[] = [];
    for (let q = 1; q <= 8; q++) {
      const idx = Math.floor((q / 9) * (vals.length - 1));
      const t = vals[idx];
      if (candidates[candidates.length - 1] !== t) candidates.push(t);
    }

    for (const thr of candidates) {
      let lSum = 0,
        lSqSum = 0,
        lN = 0,
        rSum = 0,
        rSqSum = 0,
        rN = 0;
      for (let i = 0; i < n; i++) {
        if (X[i][f] <= thr) {
          lSum += y[i];
          lSqSum += y[i] * y[i];
          lN++;
        } else {
          rSum += y[i];
          rSqSum += y[i] * y[i];
          rN++;
        }
      }
      if (lN < 2 || rN < 2) continue;
      const lSSE = lSqSum - (lSum * lSum) / lN;
      const rSSE = rSqSum - (rSum * rSum) / rN;
      const gain = parentSSE - (lSSE + rSSE);
      if (gain > bestGain) {
        bestGain = gain;
        bestFeat = f;
        bestThr = thr;
      }
    }
  }

  if (bestFeat < 0) return { leaf: mean };

  const leftIdx: number[] = [];
  const rightIdx: number[] = [];
  for (let i = 0; i < n; i++) (X[i][bestFeat] <= bestThr ? leftIdx : rightIdx).push(i);
  bestLeft = leftIdx;
  bestRight = rightIdx;

  return {
    feature: bestFeat,
    threshold: bestThr,
    left: buildTree(bestLeft.map((i) => X[i]), bestLeft.map((i) => y[i]), features, depth + 1, params),
    right: buildTree(bestRight.map((i) => X[i]), bestRight.map((i) => y[i]), features, depth + 1, params),
  };
}

function predictTree(node: TreeNode, x: number[]): number {
  if (node.leaf !== undefined) return node.leaf;
  return x[node.feature!] <= node.threshold! ? predictTree(node.left!, x) : predictTree(node.right!, x);
}

function trainGBRT(X: number[][], y: number[], params: GBRTParams = DEFAULT_PARAMS): GBRTModel {
  const rand = mulberry32(42);
  const n = y.length;
  const nFeat = X[0]?.length ?? 0;
  const base = n ? y.reduce((s, v) => s + v, 0) / n : 0;
  const preds = new Array(n).fill(base);
  const trees: TreeNode[] = [];

  for (let m = 0; m < params.nEstimators; m++) {
    const residuals = y.map((v, i) => v - preds[i]);
    // column subsampling
    const featPool = Array.from({ length: nFeat }, (_, i) => i);
    const sampleSize = Math.max(1, Math.floor(nFeat * params.subsample));
    for (let i = featPool.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [featPool[i], featPool[j]] = [featPool[j], featPool[i]];
    }
    const features = featPool.slice(0, sampleSize);
    const tree = buildTree(X, residuals, features, 0, params);
    trees.push(tree);
    for (let i = 0; i < n; i++) preds[i] += params.learningRate * predictTree(tree, X[i]);
  }

  return { base, lr: params.learningRate, trees };
}

function predictGBRT(model: GBRTModel, x: number[]): number {
  let p = model.base;
  for (const t of model.trees) p += model.lr * predictTree(t, x);
  return p;
}

// ---------------------------------------------------------------------------
// Feature engineering
// ---------------------------------------------------------------------------

const LAGS = [1, 7, 14];
const ROLLS = [7, 28];

function rollingMean(arr: number[], idx: number, window: number): number {
  const start = Math.max(0, idx - window);
  let s = 0;
  let c = 0;
  for (let i = start; i < idx; i++) {
    s += arr[i];
    c++;
  }
  return c > 0 ? s / c : 0;
}

interface FeatureBuild {
  X: number[][];
  y: number[];
}

/** Build training matrix where row i is features known *before* day i predicting day i's target. */
function buildFeatures(daily: DailyAgg[], target: "revenue" | "roas"): FeatureBuild {
  const X: number[][] = [];
  const y: number[] = [];
  const tgt = daily.map((d) => (target === "revenue" ? d.revenue : d.roas));
  const spendArr = daily.map((d) => d.spend);

  // Need at least max(LAGS, ROLLS) history before first usable row
  const start = Math.max(...LAGS, ...ROLLS);

  for (let i = start; i < daily.length; i++) {
    const d = daily[i];
    const dt = new Date(d.date);
    const dow = dt.getUTCDay();
    const month = dt.getUTCMonth();

    const row: number[] = [
      d.spend,
      d.clicks,
      d.impressions,
      d.conversions,
      dow,
      month,
      // one-hot day-of-week (gives trees easy categorical splits)
      ...Array.from({ length: 7 }, (_, k) => (k === dow ? 1 : 0)),
      // lag features of target
      ...LAGS.map((l) => tgt[i - l]),
      // rolling means of target
      ...ROLLS.map((w) => rollingMean(tgt, i, w)),
      // lag features of spend
      ...LAGS.map((l) => spendArr[i - l]),
      // rolling mean of spend
      rollingMean(spendArr, i, 7),
    ];
    X.push(row);
    y.push(tgt[i]);
  }
  return { X, y };
}

/** Build a single feature row for a future day given the working history. */
function buildFutureRow(
  history: DailyAgg[],
  futureDate: Date,
  futureExog: { spend: number; clicks: number; impressions: number; conversions: number },
  target: "revenue" | "roas",
): number[] {
  const tgt = history.map((d) => (target === "revenue" ? d.revenue : d.roas));
  const spendArr = history.map((d) => d.spend);
  const i = history.length; // predicting "next" — use last `i` values as history
  const dow = futureDate.getUTCDay();
  const month = futureDate.getUTCMonth();

  return [
    futureExog.spend,
    futureExog.clicks,
    futureExog.impressions,
    futureExog.conversions,
    dow,
    month,
    ...Array.from({ length: 7 }, (_, k) => (k === dow ? 1 : 0)),
    ...LAGS.map((l) => tgt[i - l] ?? 0),
    ...ROLLS.map((w) => rollingMean(tgt, i, w)),
    ...LAGS.map((l) => spendArr[i - l] ?? 0),
    rollingMean(spendArr, i, 7),
  ];
}

// ---------------------------------------------------------------------------
// Exogenous projection (spend / clicks / impressions / conversions)
// ---------------------------------------------------------------------------

function projectExog(daily: DailyAgg[], futureDate: Date) {
  const lookback = Math.min(28, daily.length);
  const recent = daily.slice(-lookback);
  const meanSpend = recent.reduce((s, d) => s + d.spend, 0) / lookback;
  const meanClicks = recent.reduce((s, d) => s + d.clicks, 0) / lookback;
  const meanImpr = recent.reduce((s, d) => s + d.impressions, 0) / lookback;
  const meanConv = recent.reduce((s, d) => s + d.conversions, 0) / lookback;

  // weekly seasonality factor on spend
  const dow = futureDate.getUTCDay();
  const dowVals = recent.filter((d) => new Date(d.date).getUTCDay() === dow).map((d) => d.spend);
  const dowMean = dowVals.length ? dowVals.reduce((s, v) => s + v, 0) / dowVals.length : meanSpend;
  const factor = meanSpend > 0 ? dowMean / meanSpend : 1;

  return {
    spend: Math.max(0, meanSpend * factor),
    clicks: Math.max(0, meanClicks * factor),
    impressions: Math.max(0, meanImpr * factor),
    conversions: Math.max(0, meanConv * factor),
  };
}

// ---------------------------------------------------------------------------
// Public forecasting API (compatible with existing UI)
// ---------------------------------------------------------------------------

function forecastTarget(daily: DailyAgg[], horizon: number, target: "revenue" | "roas"): ForecastPoint[] {
  if (daily.length === 0) return [];
  const minHistory = Math.max(...LAGS, ...ROLLS) + 5;
  if (daily.length < minHistory) {
    // Not enough data to train — fall back to mean projection
    const tgt = daily.map((d) => (target === "revenue" ? d.revenue : d.roas));
    const mean = tgt.reduce((s, v) => s + v, 0) / tgt.length;
    const hist: ForecastPoint[] = daily.map((d, i) => ({
      date: d.date,
      value: tgt[i],
      lower: tgt[i],
      upper: tgt[i],
      historical: true,
    }));
    const lastDate = new Date(daily[daily.length - 1].date);
    for (let h = 1; h <= horizon; h++) {
      const d = new Date(lastDate);
      d.setUTCDate(lastDate.getUTCDate() + h);
      hist.push({ date: d.toISOString().slice(0, 10), value: mean, lower: mean * 0.7, upper: mean * 1.3 });
    }
    return hist;
  }

  const { X, y } = buildFeatures(daily, target);
  const model = trainGBRT(X, y);

  // In-sample residual std
  const preds = X.map((x) => predictGBRT(model, x));
  const residuals = y.map((v, i) => v - preds[i]);
  const mean = residuals.reduce((s, v) => s + v, 0) / residuals.length;
  const variance = residuals.reduce((s, v) => s + (v - mean) ** 2, 0) / Math.max(1, residuals.length - 1);
  const stderr = Math.sqrt(variance);

  const out: ForecastPoint[] = daily.map((d, i) => {
    const v = target === "revenue" ? d.revenue : d.roas;
    return { date: d.date, value: v, lower: v, upper: v, historical: true };
  });

  const history = daily.slice();
  const lastDate = new Date(daily[daily.length - 1].date);

  for (let h = 1; h <= horizon; h++) {
    const fd = new Date(lastDate);
    fd.setUTCDate(lastDate.getUTCDate() + h);
    const exog = projectExog(history, fd);
    const row = buildFutureRow(history, fd, exog, target);
    const pred = Math.max(0, predictGBRT(model, row));
    const margin = 1.96 * stderr * Math.sqrt(1 + h / 30);

    out.push({
      date: fd.toISOString().slice(0, 10),
      value: Math.round(pred * 100) / 100,
      lower: Math.max(0, Math.round((pred - margin) * 100) / 100),
      upper: Math.round((pred + margin) * 100) / 100,
    });

    // append synthetic day to history so subsequent lags/rollings update
    const syntheticRevenue = target === "revenue" ? pred : exog.spend * pred;
    const syntheticRoas = target === "roas" ? pred : exog.spend > 0 ? pred / exog.spend : 0;
    history.push({
      date: fd.toISOString().slice(0, 10),
      spend: exog.spend,
      clicks: exog.clicks,
      impressions: exog.impressions,
      conversions: exog.conversions,
      revenue: syntheticRevenue,
      roas: syntheticRoas,
    });
  }

  return out;
}

/**
 * Legacy generic forecast hook — retained for backward compatibility with any
 * caller passing a pre-aggregated {date, value} series. Internally falls back
 * to a lightweight trend+seasonality model when no exogenous features exist.
 */
export function forecast(series: { date: string; value: number }[], horizon: number): ForecastPoint[] {
  if (series.length === 0) return [];
  // Build a synthetic DailyAgg from value-only series and forecast revenue-style
  const daily: DailyAgg[] = series.map((s) => ({
    date: s.date,
    spend: 0,
    clicks: 0,
    impressions: 0,
    conversions: 0,
    revenue: s.value,
    roas: 0,
  }));
  return forecastTarget(daily, horizon, "revenue");
}

export function forecastRevenue(rows: CampaignRow[], horizon: number): ForecastPoint[] {
  return forecastTarget(aggregateDaily(rows), horizon, "revenue");
}

export function forecastRoas(rows: CampaignRow[], horizon: number): ForecastPoint[] {
  return forecastTarget(aggregateDaily(rows), horizon, "roas");
}

// ---------------------------------------------------------------------------
// Budget simulation — drives the Budget Simulator screen
// ---------------------------------------------------------------------------

export interface SimChannelResult {
  channel: string;
  horizonDays: number;
  baselineDailySpend: number;
  newDailySpend: number;
  baselineTotalSpend: number;
  newTotalSpend: number;
  baselineRevenue: number;
  projectedRevenue: number;
  projectedRevenueLower: number;
  projectedRevenueUpper: number;
  baselineRoas: number;
  projectedRoas: number;
  daily: ForecastPoint[]; // forecast horizon only
}

/**
 * Run the gradient-boosted forecasting model for a single channel with a
 * user-supplied future daily spend. Click / impression / conversion volumes
 * are scaled proportionally to the spend change, while the booster learns
 * the non-linear revenue response from history.
 */
export function simulateChannelForecast(
  rows: CampaignRow[],
  channel: string,
  newDailySpend: number,
  horizon: number,
): SimChannelResult {
  const chRows = rows.filter((r) => r.channel === channel);
  const daily = aggregateDaily(chRows);

  const lookback = Math.min(horizon, daily.length);
  const baseSlice = daily.slice(-Math.max(1, lookback));
  const baselineDailySpend = baseSlice.reduce((s, d) => s + d.spend, 0) / Math.max(1, baseSlice.length);
  const baselineDailyRevenue = baseSlice.reduce((s, d) => s + d.revenue, 0) / Math.max(1, baseSlice.length);
  const baselineRevenue = baselineDailyRevenue * horizon;
  const baselineTotalSpend = baselineDailySpend * horizon;
  const baselineRoas = baselineTotalSpend > 0 ? baselineRevenue / baselineTotalSpend : 0;

  const minHistory = Math.max(...LAGS, ...ROLLS) + 5;
  const spendRatio = baselineDailySpend > 0 ? newDailySpend / baselineDailySpend : 1;
  const newTotalSpend = newDailySpend * horizon;

  if (daily.length < minHistory) {
    const projRev = baselineRevenue * Math.pow(Math.max(0, spendRatio), 0.85);
    return {
      channel,
      horizonDays: horizon,
      baselineDailySpend,
      newDailySpend,
      baselineTotalSpend,
      newTotalSpend,
      baselineRevenue,
      projectedRevenue: projRev,
      projectedRevenueLower: projRev * 0.75,
      projectedRevenueUpper: projRev * 1.25,
      baselineRoas,
      projectedRoas: newTotalSpend > 0 ? projRev / newTotalSpend : 0,
      daily: [],
    };
  }

  const { X, y } = buildFeatures(daily, "revenue");
  const model = trainGBRT(X, y);
  const preds = X.map((x) => predictGBRT(model, x));
  const residuals = y.map((v, i) => v - preds[i]);
  const rMean = residuals.reduce((s, v) => s + v, 0) / residuals.length;
  const variance = residuals.reduce((s, v) => s + (v - rMean) ** 2, 0) / Math.max(1, residuals.length - 1);
  const stderr = Math.sqrt(variance);

  const history = daily.slice();
  const lastDate = new Date(daily[daily.length - 1].date);
  const out: ForecastPoint[] = [];
  let sumRev = 0;
  let sumLower = 0;
  let sumUpper = 0;

  for (let h = 1; h <= horizon; h++) {
    const fd = new Date(lastDate);
    fd.setUTCDate(lastDate.getUTCDate() + h);
    const baseExog = projectExog(history, fd);
    const dowFactor = baselineDailySpend > 0 ? baseExog.spend / baselineDailySpend : 1;
    const exog = {
      spend: newDailySpend * dowFactor,
      clicks: baseExog.clicks * spendRatio,
      impressions: baseExog.impressions * spendRatio,
      conversions: baseExog.conversions * spendRatio,
    };
    const row = buildFutureRow(history, fd, exog, "revenue");
    const pred = Math.max(0, predictGBRT(model, row));
    const margin = 1.96 * stderr * Math.sqrt(1 + h / 30);
    const lower = Math.max(0, pred - margin);
    const upper = pred + margin;
    sumRev += pred;
    sumLower += lower;
    sumUpper += upper;

    out.push({
      date: fd.toISOString().slice(0, 10),
      value: Math.round(pred * 100) / 100,
      lower: Math.round(lower * 100) / 100,
      upper: Math.round(upper * 100) / 100,
    });

    history.push({
      date: fd.toISOString().slice(0, 10),
      spend: exog.spend,
      clicks: exog.clicks,
      impressions: exog.impressions,
      conversions: exog.conversions,
      revenue: pred,
      roas: exog.spend > 0 ? pred / exog.spend : 0,
    });
  }

  return {
    channel,
    horizonDays: horizon,
    baselineDailySpend,
    newDailySpend,
    baselineTotalSpend,
    newTotalSpend,
    baselineRevenue,
    projectedRevenue: sumRev,
    projectedRevenueLower: sumLower,
    projectedRevenueUpper: sumUpper,
    baselineRoas,
    projectedRoas: newTotalSpend > 0 ? sumRev / newTotalSpend : 0,
    daily: out,
  };
}
