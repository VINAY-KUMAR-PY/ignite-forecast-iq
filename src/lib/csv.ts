import type { CampaignRow, ValidationIssue, ValidationResult } from "./types";

const REQUIRED = [
  "date",
  "channel",
  "campaign_type",
  "campaign_name",
  "spend",
  "clicks",
  "impressions",
  "conversions",
  "revenue",
  "roas",
] as const;

function parseLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      if (q && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else q = !q;
    } else if (c === "," && !q) {
      out.push(cur);
      cur = "";
    } else cur += c;
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

export function parseCSV(text: string): ValidationResult {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  const issues: ValidationIssue[] = [];
  if (lines.length < 2) {
    return {
      rows: [],
      issues: [{ type: "missing", row: 0, message: "Empty file" }],
      totalRows: 0,
      validRows: 0,
    };
  }
  const header = parseLine(lines[0]).map((h) => h.toLowerCase());
  const missingCols = REQUIRED.filter((c) => !header.includes(c));
  if (missingCols.length) {
    return {
      rows: [],
      issues: [{ type: "missing", row: 0, message: `Missing columns: ${missingCols.join(", ")}` }],
      totalRows: 0,
      validRows: 0,
    };
  }

  const idx = Object.fromEntries(REQUIRED.map((c) => [c, header.indexOf(c)])) as Record<
    (typeof REQUIRED)[number],
    number
  >;
  const rows: CampaignRow[] = [];
  const seen = new Set<string>();
  const dateRe = /^\d{4}-\d{2}-\d{2}$/;

  for (let i = 1; i < lines.length; i++) {
    const cols = parseLine(lines[i]);
    const get = (k: (typeof REQUIRED)[number]) => cols[idx[k]] ?? "";
    let rowOk = true;
    const date = get("date");
    if (!dateRe.test(date) || Number.isNaN(new Date(date).getTime())) {
      issues.push({ type: "invalid_date", row: i + 1, message: `Invalid date "${date}"` });
      rowOk = false;
    }
    const nums: Record<string, number> = {};
    for (const k of ["spend", "clicks", "impressions", "conversions", "revenue", "roas"] as const) {
      const n = Number(get(k));
      if (Number.isNaN(n)) {
        issues.push({ type: "invalid_number", row: i + 1, message: `Invalid number for ${k}` });
        rowOk = false;
      }
      nums[k] = n;
    }
    if (nums.spend < 0)
      issues.push({ type: "negative_spend", row: i + 1, message: "Negative spend" });
    const key = `${date}|${get("channel")}|${get("campaign_name")}`;
    if (seen.has(key)) issues.push({ type: "duplicate", row: i + 1, message: "Duplicate row" });
    seen.add(key);
    for (const k of ["channel", "campaign_type", "campaign_name"] as const) {
      if (!get(k)) {
        issues.push({ type: "missing", row: i + 1, message: `Missing ${k}` });
        rowOk = false;
      }
    }
    if (rowOk) {
      rows.push({
        date,
        channel: get("channel"),
        campaign_type: get("campaign_type"),
        campaign_name: get("campaign_name"),
        spend: nums.spend,
        clicks: nums.clicks,
        impressions: nums.impressions,
        conversions: nums.conversions,
        revenue: nums.revenue,
        roas: nums.roas || (nums.spend > 0 ? nums.revenue / nums.spend : 0),
      });
    }
  }
  return { rows, issues, totalRows: lines.length - 1, validRows: rows.length };
}

export function toCSV(rows: CampaignRow[]): string {
  const head = REQUIRED.join(",");
  const body = rows.map((r) => REQUIRED.map((k) => r[k]).join(",")).join("\n");
  return `${head}\n${body}`;
}
