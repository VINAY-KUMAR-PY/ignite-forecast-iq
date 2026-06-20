import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowRight,
  BarChart3,
  Brain,
  Calculator,
  Database,
  LineChart,
  Sparkles,
  TrendingUp,
  Upload,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "AIgnition ForecastIQ - Ecommerce Forecasting and Budget Decisions" },
      {
        name: "description",
        content:
          "Upload GA4, Shopify, or Ads CSV data, forecast revenue and ROAS, simulate budget moves, and generate an executive decision brief.",
      },
    ],
  }),
  component: Landing,
});

function Landing() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav />
      <Hero />
      <Features />
      <ForecastingSection />
      <Benefits />
      <AIInsightsSection />
      <CTA />
      <Footer />
    </div>
  );
}

function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/70 backdrop-blur-xl">
      <div className="container mx-auto flex h-16 items-center justify-between px-6">
        <Link to="/" className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-brand shadow-glow">
            <Sparkles className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="text-lg font-semibold tracking-tight">
            AIgnition <span className="text-gradient-brand">ForecastIQ</span>
          </span>
        </Link>
        <nav className="hidden items-center gap-8 text-sm text-muted-foreground md:flex">
          <a href="#features" className="hover:text-foreground">
            Features
          </a>
          <a href="#forecasting" className="hover:text-foreground">
            Forecasting
          </a>
          <a href="#insights" className="hover:text-foreground">
            AI Insights
          </a>
          <a href="#benefits" className="hover:text-foreground">
            Benefits
          </a>
        </nav>
        <Link to="/app">
          <Button variant="hero" size="sm">
            Launch app <ArrowRight className="ml-1 h-4 w-4" />
          </Button>
        </Link>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-gradient-hero">
      <div className="container mx-auto grid gap-12 px-6 py-24 md:py-32 lg:grid-cols-2 lg:items-center">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/40 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
            <Zap className="h-3 w-3 text-primary-glow" />
            Evaluator-safe AI forecasting for ecommerce marketing
          </div>
          <h1 className="mt-6 text-5xl font-bold tracking-tight md:text-6xl">
            Turn campaign history into
            <br />
            <span className="text-gradient-brand">budget decisions</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg text-muted-foreground">
            ForecastIQ converts GA4, Shopify, and Ads exports into 30, 60, and 90 day revenue
            forecasts, ROAS projections, confidence intervals, and an executive next-budget action.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/app">
              <Button variant="hero" size="lg">
                Open Decision Center <ArrowRight className="ml-1 h-4 w-4" />
              </Button>
            </Link>
            <a href="#features">
              <Button variant="outline" size="lg">
                See features
              </Button>
            </a>
          </div>
          <dl className="mt-12 grid grid-cols-3 gap-6 border-t border-border/60 pt-6">
            <Stat label="Forecast horizon" value="90d" />
            <Stat label="Data sources" value="3+" />
            <Stat label="Evaluator mode" value="Offline" />
          </dl>
        </div>
        <div className="relative">
          <div className="absolute -inset-4 rounded-3xl bg-gradient-brand opacity-30 blur-3xl" />
          <div className="relative rounded-2xl border border-border/60 bg-gradient-card p-6 shadow-elevated">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Projected Revenue (next 90d)</span>
              <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success">
                +18.4%
              </span>
            </div>
            <div className="mt-2 text-4xl font-bold tracking-tight">$2.41M</div>
            <MiniChart />
            <div className="mt-6 grid grid-cols-3 gap-3 text-center text-xs">
              {[
                { l: "Google", v: "4.6x", c: "var(--chart-1)" },
                { l: "Meta", v: "3.2x", c: "var(--chart-3)" },
                { l: "Bing", v: "5.4x", c: "var(--chart-5)" },
              ].map((c) => (
                <div key={c.l} className="rounded-lg border border-border/60 bg-card/40 p-3">
                  <div className="text-muted-foreground">{c.l}</div>
                  <div className="mt-1 text-base font-semibold" style={{ color: c.c }}>
                    {c.v}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold">{value}</dd>
    </div>
  );
}

function MiniChart() {
  const pts = Array.from(
    { length: 40 },
    (_, i) => 50 + 20 * Math.sin(i / 4) + i * 1.2 + (i > 25 ? (i - 25) * 2.5 : 0),
  );
  const max = Math.max(...pts);
  const path = pts
    .map(
      (p, i) => `${i === 0 ? "M" : "L"} ${(i / (pts.length - 1)) * 100} ${100 - (p / max) * 100}`,
    )
    .join(" ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="mt-4 h-32 w-full">
      <defs>
        <linearGradient id="g" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="oklch(0.7 0.2 265)" stopOpacity="0.5" />
          <stop offset="100%" stopColor="oklch(0.7 0.2 265)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L 100 100 L 0 100 Z`} fill="url(#g)" />
      <path d={path} stroke="oklch(0.7 0.2 265)" strokeWidth="1.2" fill="none" />
      <path
        d={path
          .replace(/M 0 [\d.]+/, (m) => m)
          .replace(/L (\d+\.?\d*) /g, (m, x) => (Number(x) > 65 ? `L ${x} ` : m))}
        stroke="oklch(0.78 0.18 195)"
        strokeWidth="1.2"
        strokeDasharray="2 2"
        fill="none"
      />
    </svg>
  );
}

function Features() {
  const items = [
    {
      icon: BarChart3,
      title: "Executive Decision Center",
      desc: "Best budget action, expected impact, confidence, risk, and next steps in one judge-ready view.",
    },
    {
      icon: Upload,
      title: "GA4 / Shopify / Ads upload",
      desc: "Schema adapters normalize ecommerce exports before duplicate, date, spend, and revenue validation.",
    },
    {
      icon: LineChart,
      title: "Revenue & ROAS forecasts",
      desc: "30 / 60 / 90 day forecasts at overall, channel, campaign-type or campaign level.",
    },
    {
      icon: Calculator,
      title: "Budget simulator",
      desc: "Slide budgets across Google, Meta and Microsoft Ads and see revenue and ROAS update live.",
    },
    {
      icon: Brain,
      title: "AI executive insights",
      desc: "Gemini-backed or deterministic fallback briefs with drivers, risks, opportunities, and action plans.",
    },
    {
      icon: Database,
      title: "Evaluator-safe mode",
      desc: "The offline runner loads a trained model, writes predictions.csv, and never starts a server.",
    },
  ];
  return (
    <section id="features" className="border-t border-border/60 py-24">
      <div className="container mx-auto px-6">
        <SectionHeader eyebrow="Platform" title="Everything you need to forecast and grow" />
        <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {items.map((i) => (
            <div
              key={i.title}
              className="group rounded-2xl border border-border/60 bg-gradient-card p-6 transition hover:shadow-elevated"
            >
              <div className="grid h-10 w-10 place-items-center rounded-lg bg-gradient-brand shadow-glow">
                <i.icon className="h-5 w-5 text-primary-foreground" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">{i.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{i.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ForecastingSection() {
  return (
    <section id="forecasting" className="border-t border-border/60 bg-muted/30 py-24">
      <div className="container mx-auto grid gap-12 px-6 lg:grid-cols-2 lg:items-center">
        <div>
          <SectionHeader
            eyebrow="Forecasting"
            title="Predict the next 90 days with confidence"
            align="left"
          />
          <ul className="mt-8 space-y-4 text-sm">
            {[
              "Trained evaluator model with calibrated confidence intervals",
              "Forecast at overall, channel, campaign-type or campaign level",
              "Lower / Expected / Upper bounds visualised on every chart",
              "Offline-safe predictions with safe baseline fallback for hidden datasets",
            ].map((t) => (
              <li key={t} className="flex items-start gap-3">
                <TrendingUp className="mt-0.5 h-4 w-4 shrink-0 text-primary-glow" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl border border-border/60 bg-gradient-card p-6 shadow-elevated">
          <div className="text-sm text-muted-foreground">Revenue - 90-day forecast</div>
          <MiniChart />
          <div className="grid grid-cols-3 gap-3 text-center text-xs">
            {[
              { l: "Lower", v: "$1.92M" },
              { l: "Expected", v: "$2.41M" },
              { l: "Upper", v: "$2.84M" },
            ].map((s) => (
              <div key={s.l} className="rounded-lg border border-border/60 bg-card/40 p-3">
                <div className="text-muted-foreground">{s.l}</div>
                <div className="mt-1 font-semibold">{s.v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Benefits() {
  const items = [
    {
      title: "Plan budgets with data",
      desc: "Replace gut-feel media planning with statistical forecasts and AI commentary.",
    },
    {
      title: "Spot risk before it hurts",
      desc: "Catch underperforming campaigns and channel decay in your weekly review.",
    },
    {
      title: "Win the QBR",
      desc: "Export-ready insights, projections and recommendations for the leadership team.",
    },
  ];
  return (
    <section id="benefits" className="border-t border-border/60 py-24">
      <div className="container mx-auto px-6">
        <SectionHeader eyebrow="Benefits" title="Built for marketing teams that need to ship" />
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {items.map((b) => (
            <div key={b.title} className="rounded-2xl border border-border/60 bg-gradient-card p-6">
              <h3 className="text-lg font-semibold">{b.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{b.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function AIInsightsSection() {
  return (
    <section id="insights" className="border-t border-border/60 bg-muted/30 py-24">
      <div className="container mx-auto grid gap-12 px-6 lg:grid-cols-2 lg:items-center">
        <div className="rounded-2xl border border-border/60 bg-gradient-card p-6 shadow-elevated">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-primary-glow">
            <Brain className="h-4 w-4" /> Executive briefing
          </div>
          <h4 className="mt-3 text-lg font-semibold">Q4 outlook</h4>
          <p className="mt-2 text-sm text-muted-foreground">
            Revenue is trending +18% QoQ driven by Performance Max and branded search. Meta
            retargeting ROAS slipped to 1.9x; reallocating 15% of its spend to Google PMax projects
            an additional $142K in the next 30 days.
          </p>
          <div className="mt-4 grid gap-2 text-xs">
            {[
              "Action: Shift 15% Meta retargeting to Google PMax",
              "Risk: Bing Generic CPC up 22% MoM; bid cap recommended",
              "Protect: Brand Search ROAS 6.8x; protect budget",
            ].map((l) => (
              <div key={l} className="rounded-md bg-card/40 px-3 py-2">
                {l}
              </div>
            ))}
          </div>
        </div>
        <div>
          <SectionHeader
            eyebrow="AI Insights"
            title="A virtual analyst on your team"
            align="left"
          />
          <p className="mt-4 text-muted-foreground">
            ForecastIQ turns your campaign data into a board-ready brief: revenue drivers, risks,
            opportunities, channel performance and concrete budget reallocation recommendations.
          </p>
          <Link to="/app/insights" className="mt-6 inline-block">
            <Button variant="hero">
              Generate insights <Sparkles className="ml-1 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="border-t border-border/60 py-24">
      <div className="container mx-auto px-6">
        <div className="relative overflow-hidden rounded-3xl border border-border/60 bg-gradient-hero p-12 text-center shadow-elevated">
          <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
            Ready to forecast your next quarter?
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
            Launch the judge demo workspace with 365 days of multi-channel data already loaded.
          </p>
          <Link to="/app" className="mt-8 inline-block">
            <Button variant="hero" size="lg">
              Open the Decision Center <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}

function SectionHeader({
  eyebrow,
  title,
  align = "center",
}: {
  eyebrow: string;
  title: string;
  align?: "left" | "center";
}) {
  return (
    <div className={align === "center" ? "mx-auto max-w-2xl text-center" : ""}>
      <div className="text-xs font-medium uppercase tracking-wider text-primary-glow">
        {eyebrow}
      </div>
      <h2 className="mt-3 text-3xl font-bold tracking-tight md:text-4xl">{title}</h2>
    </div>
  );
}

function Footer() {
  return (
    <footer className="border-t border-border/60 py-10">
      <div className="container mx-auto flex flex-col items-center justify-between gap-4 px-6 text-sm text-muted-foreground md:flex-row">
        <div>(c) {new Date().getFullYear()} AIgnition ForecastIQ. Built for hackathon demos.</div>
        <div className="flex gap-6">
          <Link to="/app">App</Link>
          <a href="#features">Features</a>
          <a href="#insights">AI Insights</a>
        </div>
      </div>
    </footer>
  );
}
