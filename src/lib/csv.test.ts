import { describe, expect, it } from "vitest";
import { parseCSV, toCSV } from "./csv";

describe("CSV business logic", () => {
  it("normalizes aliased headers, whitespace, quoted currency, and ROAS defaults", () => {
    const result = parseCSV(
      [
        " Day , Platform , Campaign , Campaign_Type , Cost , Clicks , Impressions , Conversions , Sales ",
        ' 2026-01-01 , google , Brand Search , Search , "$1,234.56" , 50 , 1000 , 5 , "$4,938.24" ',
      ].join("\n"),
    );

    expect(result.issues).toEqual([]);
    expect(result.validRows).toBe(1);
    expect(result.rows[0]).toMatchObject({
      date: "2026-01-01",
      channel: "Google Ads",
      campaign_name: "Brand Search",
      campaign_type: "Search",
      spend: 1234.56,
      revenue: 4938.24,
      roas: 4,
    });
  });

  it("reports missing date headers before parsing rows", () => {
    const result = parseCSV("campaign,spend,revenue\nBrand,100,400\n");

    expect(result.rows).toEqual([]);
    expect(result.issues[0]).toMatchObject({
      type: "missing",
      row: 0,
      message: "Missing date column or supported date alias",
    });
  });

  it("drops invalid rows but keeps duplicate warnings visible", () => {
    const result = parseCSV(
      [
        "date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue",
        "2026-01-01,Google Ads,Search,Brand,-10,10,100,1,400",
        "2026-01-02,Google Ads,Search,Brand,100,10,100,1,400",
        "2026-01-02,Google Ads,Search,Brand,100,10,100,1,400",
      ].join("\n"),
    );

    expect(result.validRows).toBe(2);
    expect(result.issues.map((issue) => issue.type)).toContain("negative_spend");
    expect(result.issues.map((issue) => issue.type)).toContain("duplicate");
  });

  it("serializes canonical rows with stable evaluator-style column order", () => {
    const csv = toCSV([
      {
        date: "2026-01-01",
        channel: "Meta Ads",
        campaign_type: "Paid Social",
        campaign_name: "Prospecting",
        spend: 100,
        clicks: 20,
        impressions: 500,
        conversions: 4,
        revenue: 250,
        roas: 2.5,
      },
    ]);

    expect(csv.split("\n")[0]).toBe(
      "date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue,roas",
    );
    expect(csv).toContain("2026-01-01,Meta Ads,Paid Social,Prospecting,100,20,500,4,250,2.5");
  });
});
