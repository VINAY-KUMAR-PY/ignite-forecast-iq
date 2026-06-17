export const fmtCurrency = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);

export const fmtCompact = (n: number) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n);

export const fmtNumber = (n: number) => new Intl.NumberFormat("en-US").format(Math.round(n));

export const fmtPct = (n: number) => `${(n * 100).toFixed(1)}%`;

export const fmtRoas = (n: number) => `${n.toFixed(2)}x`;

export const fmtDate = (d: string) =>
  new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
