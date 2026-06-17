import type { CampaignRow, Channel } from "./types";

const CHANNELS: {
  name: Channel;
  types: string[];
  campaigns: string[];
  baseRoas: number;
  baseSpend: number;
}[] = [
  {
    name: "Google Ads",
    types: ["Search", "Shopping", "Performance Max"],
    campaigns: [
      "Brand Search",
      "Generic Search",
      "Shopping - Best Sellers",
      "PMax - Holiday",
      "Competitor",
    ],
    baseRoas: 4.2,
    baseSpend: 1800,
  },
  {
    name: "Meta Ads",
    types: ["Prospecting", "Retargeting", "Advantage+"],
    campaigns: [
      "Prospecting - Lookalike",
      "Retargeting - Cart",
      "Advantage+ Shopping",
      "Engagement",
      "Reels Ads",
    ],
    baseRoas: 3.1,
    baseSpend: 1500,
  },
  {
    name: "Microsoft Ads",
    types: ["Search", "Shopping"],
    campaigns: ["Bing Brand", "Bing Generic", "Bing Shopping"],
    baseRoas: 5.1,
    baseSpend: 600,
  },
];

// deterministic pseudo-random for repeatability
function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

export function generateDemoData(days = 365): CampaignRow[] {
  const rand = seeded(42);
  const rows: CampaignRow[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let d = days - 1; d >= 0; d--) {
    const date = new Date(today);
    date.setDate(today.getDate() - d);
    const iso = date.toISOString().slice(0, 10);
    const dayOfWeek = date.getDay();
    const dayOfYear = Math.floor(
      (date.getTime() - new Date(date.getFullYear(), 0, 0).getTime()) / 86400000,
    );

    // seasonality: yearly + weekly + slight growth trend
    const yearly = 1 + 0.25 * Math.sin((dayOfYear / 365) * Math.PI * 2 - Math.PI / 2);
    const weekend = dayOfWeek === 0 || dayOfWeek === 6 ? 0.85 : 1.05;
    const trend = 1 + (days - d) / days / 2; // ~50% growth across year

    for (const ch of CHANNELS) {
      for (const campaign of ch.campaigns) {
        const type = ch.types[campaign.length % ch.types.length];
        const noise = 0.7 + rand() * 0.6;
        const spend = Math.round(ch.baseSpend * 0.2 * yearly * weekend * trend * noise * 100) / 100;
        const roasNoise = 0.75 + rand() * 0.5;
        const roas =
          Math.round(ch.baseRoas * roasNoise * (campaign.includes("Brand") ? 1.4 : 1) * 100) / 100;
        const revenue = Math.round(spend * roas * 100) / 100;
        const impressions = Math.round(spend * (40 + rand() * 60));
        const clicks = Math.round(impressions * (0.015 + rand() * 0.03));
        const conversions = Math.round(clicks * (0.02 + rand() * 0.05));
        rows.push({
          date: iso,
          channel: ch.name,
          campaign_type: type,
          campaign_name: campaign,
          spend,
          clicks,
          impressions,
          conversions,
          revenue,
          roas,
        });
      }
    }
  }
  return rows;
}
