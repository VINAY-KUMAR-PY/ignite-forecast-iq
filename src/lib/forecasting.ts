import type { CampaignRow, ForecastPoint } from "./types";

export interface DailyAgg {
  date: string;
  spend: number;
  revenue: number;
  roas: number;
}

export function aggregateDaily(rows: CampaignRow[]): DailyAgg[] {
  const map = new Map<string, { spend: number; revenue: number }>();
  for (const r of rows) {
    const cur = map.get(r.date) ?? { spend: 0, revenue: 0 };
    cur.spend += r.spend;
    cur.revenue += r.revenue;
    map.set(r.date, cur);
  }
  return [...map.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([date, v]) => ({ date, spend: v.spend, revenue: v.revenue, roas: v.spend > 0 ? v.revenue / v.spend : 0 }));
}

// Linear regression on index → value
function linreg(values: number[]) {
  const n = values.length;
  let sx = 0,
    sy = 0,
    sxy = 0,
    sxx = 0;
  for (let i = 0; i < n; i++) {
    sx += i;
    sy += values[i];
    sxy += i * values[i];
    sxx += i * i;
  }
  const slope = (n * sxy - sx * sy) / Math.max(1, n * sxx - sx * sx);
  const intercept = (sy - slope * sx) / n;
  // residual stdev
  let ss = 0;
  for (let i = 0; i < n; i++) {
    const pred = intercept + slope * i;
    ss += (values[i] - pred) ** 2;
  }
  const stderr = Math.sqrt(ss / Math.max(1, n - 2));
  return { slope, intercept, stderr };
}

/**
 * Forecast with linear trend + weekly seasonality.
 * Returns historical + forecast points.
 */
export function forecast(series: { date: string; value: number }[], horizon: number): ForecastPoint[] {
  if (series.length === 0) return [];
  const values = series.map((s) => s.value);
  const { slope, intercept, stderr } = linreg(values);

  // weekly seasonal factor
  const dow = series.map((s) => new Date(s.date).getDay());
  const dowSum = Array(7).fill(0);
  const dowCnt = Array(7).fill(0);
  for (let i = 0; i < series.length; i++) {
    const trend = intercept + slope * i;
    const factor = trend > 0 ? values[i] / trend : 1;
    dowSum[dow[i]] += factor;
    dowCnt[dow[i]]++;
  }
  const dowFactor = dowSum.map((s, i) => (dowCnt[i] > 0 ? s / dowCnt[i] : 1));

  const out: ForecastPoint[] = series.map((s, i) => ({
    date: s.date,
    value: s.value,
    lower: s.value,
    upper: s.value,
    historical: true,
  }));

  const lastDate = new Date(series[series.length - 1].date);
  for (let h = 1; h <= horizon; h++) {
    const idx = series.length - 1 + h;
    const d = new Date(lastDate);
    d.setDate(lastDate.getDate() + h);
    const trend = intercept + slope * idx;
    const seasonal = dowFactor[d.getDay()];
    const pred = Math.max(0, trend * seasonal);
    // widening interval with sqrt(h)
    const margin = 1.96 * stderr * Math.sqrt(1 + h / 30);
    out.push({
      date: d.toISOString().slice(0, 10),
      value: Math.round(pred * 100) / 100,
      lower: Math.max(0, Math.round((pred - margin) * 100) / 100),
      upper: Math.round((pred + margin) * 100) / 100,
    });
  }
  return out;
}

export function forecastRevenue(rows: CampaignRow[], horizon: number) {
  const daily = aggregateDaily(rows);
  return forecast(
    daily.map((d) => ({ date: d.date, value: d.revenue })),
    horizon,
  );
}

export function forecastRoas(rows: CampaignRow[], horizon: number) {
  const daily = aggregateDaily(rows);
  return forecast(
    daily.map((d) => ({ date: d.date, value: d.roas })),
    horizon,
  );
}

export function filterRows(
  rows: CampaignRow[],
  filter: { level: "overall" | "channel" | "campaign_type" | "campaign"; value?: string },
): CampaignRow[] {
  if (filter.level === "overall" || !filter.value) return rows;
  const key = filter.level === "channel" ? "channel" : filter.level === "campaign_type" ? "campaign_type" : "campaign_name";
  return rows.filter((r) => r[key] === filter.value);
}
