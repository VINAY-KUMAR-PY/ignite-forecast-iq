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
export const MAX_UPLOAD_ROWS = 20000;

type CanonicalColumn = (typeof REQUIRED)[number];

const ALIASES: Record<CanonicalColumn, string[]> = {
  date: [
    "date",
    "day",
    "dt",
    "ds",
    "report_date",
    "reporting_date",
    "order_date",
    "transaction_date",
    "created_at",
    "event_date",
  ],
  channel: [
    "channel",
    "platform",
    "source",
    "traffic_source",
    "marketing_channel",
    "media_channel",
    "ad_channel",
    "network",
    "publisher",
    "sessionSource",
    "session_source",
    "source_medium",
  ],
  campaign_type: [
    "campaign_type",
    "campaign_category",
    "type",
    "objective",
    "campaign_objective",
    "funnel_stage",
    "advertising_channel_type",
    "product_type",
    "sessionMedium",
    "session_medium",
  ],
  campaign_name: [
    "campaign",
    "campaign_name",
    "campaignname",
    "campaign_id",
    "ad_campaign",
    "sessionCampaignName",
    "session_campaign_name",
    "product_title",
    "product_name",
    "product_type",
  ],
  spend: ["spend", "cost", "amount_spent", "ad_spend", "media_spend", "investment"],
  clicks: ["clicks", "click", "link_clicks", "ad_clicks", "sessions"],
  impressions: ["impressions", "impression", "impr", "views", "ad_impressions"],
  conversions: ["conversions", "conversion", "purchases", "orders", "transactions", "leads"],
  revenue: [
    "revenue",
    "sales",
    "conversion_value",
    "purchaseRevenue",
    "purchase_revenue",
    "eventValue",
    "event_value",
    "purchase_value",
    "total_price",
    "total_revenue",
    "gross_revenue",
    "value",
  ],
  roas: ["roas", "return_on_ad_spend"],
};

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

function normalizeHeader(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function aliasIndexes(header: string[], key: CanonicalColumn) {
  const wanted = new Set(ALIASES[key].map(normalizeHeader));
  return header.map((name, index) => (wanted.has(name) ? index : -1)).filter((index) => index >= 0);
}

function firstValue(cols: string[], indexes: number[]) {
  for (const index of indexes) {
    const value = cols[index]?.trim() ?? "";
    if (value && !["nan", "none", "null"].includes(value.toLowerCase())) return value;
  }
  return "";
}

function parseDate(value: string) {
  const raw = value.trim();
  if (/^\d{8}$/.test(raw)) return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 10);
}

function friendlyChannel(value: string) {
  const key = value.toLowerCase();
  if (key.includes("google")) return "Google Ads";
  if (key.includes("facebook") || key.includes("instagram") || key.includes("meta"))
    return "Meta Ads";
  if (key.includes("bing") || key.includes("microsoft")) return "Microsoft Ads";
  if (key.includes("shopify")) return "Shopify";
  return value;
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
  if (lines.length - 1 > MAX_UPLOAD_ROWS) {
    return {
      rows: [],
      issues: [
        {
          type: "too_many_rows",
          row: 0,
          message: `File has ${(lines.length - 1).toLocaleString()} rows; maximum supported upload is ${MAX_UPLOAD_ROWS.toLocaleString()} rows`,
        },
      ],
      totalRows: lines.length - 1,
      validRows: 0,
    };
  }

  const rawHeader = parseLine(lines[0]);
  const header = rawHeader.map(normalizeHeader);
  const indexes = Object.fromEntries(
    REQUIRED.map((key) => [key, aliasIndexes(header, key)]),
  ) as Record<CanonicalColumn, number[]>;
  if (!indexes.date.length) {
    return {
      rows: [],
      issues: [{ type: "missing", row: 0, message: "Missing date column or supported date alias" }],
      totalRows: lines.length - 1,
      validRows: 0,
    };
  }

  const rows: CampaignRow[] = [];
  const seen = new Set<string>();
  const sourceIndexes = rawHeader
    .map((name, index) =>
      ["sessionsource", "session_source", "source"].includes(normalizeHeader(name)) ? index : -1,
    )
    .filter((index) => index >= 0);
  const mediumIndexes = rawHeader
    .map((name, index) =>
      ["sessionmedium", "session_medium", "medium"].includes(normalizeHeader(name)) ? index : -1,
    )
    .filter((index) => index >= 0);

  for (let i = 1; i < lines.length; i++) {
    const cols = parseLine(lines[i]);
    const get = (key: CanonicalColumn) => firstValue(cols, indexes[key]);
    const source = firstValue(cols, sourceIndexes);
    const medium = firstValue(cols, mediumIndexes);
    const sourceMedium = [source, medium].filter(Boolean).join(" / ");
    let rowOk = true;

    const date = parseDate(get("date"));
    if (!date) {
      issues.push({ type: "invalid_date", row: i + 1, message: `Invalid date "${get("date")}"` });
      rowOk = false;
    }

    const numberFor = (key: CanonicalColumn, defaultValue = 0) => {
      const raw = get(key);
      if (!raw) return defaultValue;
      const n = Number(raw.replace(/[$,]/g, ""));
      if (Number.isNaN(n) || !Number.isFinite(n)) {
        issues.push({ type: "invalid_number", row: i + 1, message: `Invalid number for ${key}` });
        return defaultValue;
      }
      return n;
    };

    const nums = {
      spend: numberFor("spend"),
      clicks: numberFor("clicks"),
      impressions: numberFor("impressions"),
      conversions: numberFor("conversions"),
      revenue: numberFor("revenue"),
      roas: numberFor("roas", Number.NaN),
    };
    if (nums.spend < 0) {
      issues.push({ type: "negative_spend", row: i + 1, message: "Negative spend" });
      rowOk = false;
    }
    if (nums.revenue < 0) {
      issues.push({ type: "invalid_revenue", row: i + 1, message: "Negative revenue" });
      rowOk = false;
    }

    const channel = friendlyChannel(get("channel") || sourceMedium || "Unknown Channel");
    const campaignType = get("campaign_type") || medium || "Unclassified";
    const campaignName = get("campaign_name") || sourceMedium || "Unknown Campaign";
    const key = `${date}|${channel}|${campaignName}`;
    if (seen.has(key)) issues.push({ type: "duplicate", row: i + 1, message: "Duplicate row" });
    seen.add(key);

    if (rowOk) {
      rows.push({
        date,
        channel,
        campaign_type: campaignType,
        campaign_name: campaignName,
        spend: nums.spend,
        clicks: nums.clicks,
        impressions: nums.impressions,
        conversions: nums.conversions,
        revenue: nums.revenue,
        roas: Number.isFinite(nums.roas)
          ? nums.roas
          : nums.spend > 0
            ? nums.revenue / nums.spend
            : 0,
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
