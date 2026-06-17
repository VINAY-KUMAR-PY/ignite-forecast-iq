import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

const ChannelStat = z.object({
  name: z.string(),
  revenue: z.number(),
  spend: z.number(),
  roas: z.number(),
  sharePct: z.number().optional(),
  forecast30dRevenue: z.number().optional(),
  forecast30dRoas: z.number().optional(),
  revenueTrendPct: z.number().optional(),
});

const CampaignStat = z.object({
  name: z.string(),
  channel: z.string(),
  campaignType: z.string().optional(),
  revenue: z.number(),
  roas: z.number(),
  spend: z.number(),
  conversions: z.number().optional(),
});

const InsightsInput = z.object({
  summary: z.object({
    totalRevenue: z.number(),
    totalSpend: z.number(),
    avgRoas: z.number(),
    totalCampaigns: z.number(),
    revenueTrendPct: z.number(),
    spendTrendPct: z.number().optional(),
    roasTrendPct: z.number().optional(),
    forecast30dRevenue: z.number(),
    forecast60dRevenue: z.number().optional(),
    forecast90dRevenue: z.number().optional(),
    forecast30dRevenueLower: z.number().optional(),
    forecast30dRevenueUpper: z.number().optional(),
    forecast30dRoas: z.number().optional(),
    channels: z.array(ChannelStat),
    topCampaigns: z.array(CampaignStat),
    bottomCampaigns: z.array(CampaignStat),
    campaignTypeBreakdown: z
      .array(z.object({ type: z.string(), revenue: z.number(), spend: z.number(), roas: z.number() }))
      .optional(),
  }),
});

export interface InsightsResponse {
  executiveSummary: string;
  revenueDrivers: Array<{ title: string; detail: string; metric?: string }>;
  channelPerformance: Array<{
    channel: string;
    verdict: "outperforming" | "on_track" | "underperforming";
    insight: string;
    recommendation: string;
  }>;
  campaignPerformance: {
    top: Array<{ name: string; channel: string; insight: string }>;
    bottom: Array<{ name: string; channel: string; issue: string; action: string }>;
  };
  budgetAllocation: Array<{
    channel: string;
    currentSharePct: number;
    recommendedSharePct: number;
    rationale: string;
    expectedImpact: string;
  }>;
  risks: Array<{
    title: string;
    severity: "low" | "medium" | "high";
    description: string;
    mitigation: string;
  }>;
  growthOpportunities: Array<{
    title: string;
    description: string;
    expectedImpact: string;
    effort: "low" | "medium" | "high";
  }>;
}

export const generateInsights = createServerFn({ method: "POST" })
  .inputValidator((data: unknown) => InsightsInput.parse(data))
  .handler(async ({ data }): Promise<InsightsResponse> => {
    const key = process.env.LOVABLE_API_KEY;
    if (!key) throw new Error("Missing LOVABLE_API_KEY");

    const system = `You are a CMO-level digital marketing strategist producing board-ready briefings for an ecommerce business.
Your job: turn raw campaign performance and forecast data into specific, quantified, executive-grade recommendations.
Rules:
- Cite actual numbers (currency, ROAS, %) from the supplied data — never invent.
- Reference real channel names and campaign names from the input.
- Every recommendation must include the action AND the expected outcome.
- Budget reallocations must sum to ~100% and reference current vs recommended share.
- Be opinionated. No filler, no platitudes.
- Output STRICT JSON matching the schema. No prose, no markdown fences.`;

    const user = `Generate an executive briefing for this ecommerce marketing performance.

DATA:
${JSON.stringify(data.summary, null, 2)}

Produce JSON exactly matching this schema (no extra keys):
{
  "executiveSummary": "3-4 sentences. State current performance, trend direction, 30-day forecast vs current, and the single biggest decision the team should make.",
  "revenueDrivers": [
    { "title": "short label", "detail": "1-2 sentences referencing specific channel/campaign/segment", "metric": "the key supporting number" }
  ],
  "channelPerformance": [
    { "channel": "exact channel name", "verdict": "outperforming|on_track|underperforming", "insight": "what the data shows with numbers", "recommendation": "specific action" }
  ],
  "campaignPerformance": {
    "top": [ { "name": "real campaign name", "channel": "channel", "insight": "why it works, cite ROAS/revenue" } ],
    "bottom": [ { "name": "real campaign name", "channel": "channel", "issue": "what's wrong with numbers", "action": "pause/optimize/restructure + how" } ]
  },
  "budgetAllocation": [
    { "channel": "channel name", "currentSharePct": number, "recommendedSharePct": number, "rationale": "why shift", "expectedImpact": "quantified revenue/ROAS lift" }
  ],
  "risks": [
    { "title": "short label", "severity": "low|medium|high", "description": "what could go wrong, grounded in the data", "mitigation": "concrete preventive action" }
  ],
  "growthOpportunities": [
    { "title": "short label", "description": "the opportunity with supporting numbers", "expectedImpact": "projected $ or % lift", "effort": "low|medium|high" }
  ]
}

Requirements:
- revenueDrivers: 3-5 items
- channelPerformance: one entry per channel in the data
- campaignPerformance.top: 3 items, .bottom: 3 items
- budgetAllocation: one entry per channel, recommendedSharePct values must sum to 100
- risks: 3-4 items
- growthOpportunities: 3-5 items`;

    const res = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        model: "google/gemini-3-flash-preview",
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
        response_format: { type: "json_object" },
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      if (res.status === 429) throw new Error("AI rate limit reached. Please try again shortly.");
      if (res.status === 402) throw new Error("AI credits exhausted. Add credits in your workspace billing.");
      throw new Error(`AI gateway error ${res.status}: ${text}`);
    }
    const json = await res.json();
    const content = json.choices?.[0]?.message?.content ?? "{}";
    try {
      return JSON.parse(content) as InsightsResponse;
    } catch {
      throw new Error("AI returned invalid JSON");
    }
  });
