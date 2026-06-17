export type Channel = "Google Ads" | "Meta Ads" | "Microsoft Ads";

export interface CampaignRow {
  date: string; // ISO YYYY-MM-DD
  channel: string;
  campaign_type: string;
  campaign_name: string;
  spend: number;
  clicks: number;
  impressions: number;
  conversions: number;
  revenue: number;
  roas: number;
}

export interface ValidationIssue {
  type: string;
  row: number;
  message: string;
}

export interface ValidationResult {
  rows: CampaignRow[];
  issues: ValidationIssue[];
  totalRows: number;
  validRows: number;
}

export interface ForecastPoint {
  date: string;
  value: number;
  lower: number;
  upper: number;
  historical?: boolean;
}
