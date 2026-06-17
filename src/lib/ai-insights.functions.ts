import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

const InsightsInput = z.object({
  summary: z.object({
    totalRevenue: z.number(),
    totalSpend: z.number(),
    avgRoas: z.number(),
    totalCampaigns: z.number(),
    channels: z.array(
      z.object({
        name: z.string(),
        revenue: z.number(),
        spend: z.number(),
        roas: z.number(),
      }),
    ),
    topCampaigns: z.array(
      z.object({ name: z.string(), channel: z.string(), revenue: z.number(), roas: z.number(), spend: z.number() }),
    ),
    bottomCampaigns: z.array(
      z.object({ name: z.string(), channel: z.string(), revenue: z.number(), roas: z.number(), spend: z.number() }),
    ),
    forecast30dRevenue: z.number(),
    revenueTrendPct: z.number(),
  }),
});

interface InsightsResponse {
  executiveSummary: string;
  revenueDrivers: string[];
  topChannels: string[];
  underperformingCampaigns: string[];
  risks: string[];
  opportunities: string[];
  budgetRecommendations: string[];
  growthRecommendations: string[];
}

export const generateInsights = createServerFn({ method: "POST" })
  .inputValidator((data: unknown) => InsightsInput.parse(data))
  .handler(async ({ data }): Promise<InsightsResponse> => {
    const key = process.env.LOVABLE_API_KEY;
    if (!key) throw new Error("Missing LOVABLE_API_KEY");

    const system =
      "You are a senior digital marketing analyst producing concise, executive-ready insights. Return STRICT JSON matching the schema. Use specific numbers from the data. Be actionable.";
    const user = `Analyze this ecommerce marketing performance data and produce insights as JSON.

Data summary:
${JSON.stringify(data.summary, null, 2)}

Respond with JSON only, no markdown. Schema:
{
  "executiveSummary": "2-3 sentence overview citing key numbers",
  "revenueDrivers": ["3-5 bullets identifying what drove revenue"],
  "topChannels": ["3 bullets describing best performing channels with metrics"],
  "underperformingCampaigns": ["3-5 bullets with specific campaign names and why they underperform"],
  "risks": ["3-4 risks based on the data"],
  "opportunities": ["3-5 specific opportunities"],
  "budgetRecommendations": ["3-5 concrete budget reallocation recommendations with channel names and rationale"],
  "growthRecommendations": ["3-5 strategic growth moves"]
}`;

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
