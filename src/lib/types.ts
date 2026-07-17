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

export type DataReadinessRating = "Excellent" | "Good" | "Usable with caution" | "Needs attention";

export interface DataReadinessComponent {
  key:
    | "schema_required"
    | "completeness_validity"
    | "historical_coverage"
    | "freshness"
    | "channel_campaign_coverage"
    | "spend_revenue_consistency"
    | "outliers_duplicates";
  label: string;
  score: number;
  weight: number;
  summary: string;
}

export interface DataReadinessScore {
  score: number;
  rating: DataReadinessRating;
  components: DataReadinessComponent[];
  positiveEvidence: string[];
  warnings: string[];
  recommendedActions: string[];
  confidenceExplanation: string;
  evaluatedAsOf: string;
  metrics: Record<string, string | number | boolean>;
}

export interface ValidationResult {
  rows: CampaignRow[];
  issues: ValidationIssue[];
  totalRows: number;
  validRows: number;
  dataReadiness?: DataReadinessScore | null;
}

export interface ForecastPoint {
  date: string;
  value: number;
  lower: number;
  upper: number;
  historical?: boolean;
}
