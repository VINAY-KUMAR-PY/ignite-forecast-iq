import React, { useEffect, useRef, useState } from "react";
import { createFileRoute, Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import {
  BarChart3,
  Brain,
  Calculator,
  Check,
  ChevronLeft,
  ChevronRight,
  LineChart,
  Moon,
  RotateCcw,
  Sparkles,
  Sun,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useTheme } from "@/lib/theme";
import { useData, type WorkflowStep } from "@/lib/data-store";
import { Badge } from "@/components/ui/badge";

export const Route = createFileRoute("/app")({
  head: () => ({
    meta: [
      { title: "Decision Center - ForecastIQ" },
      { name: "description", content: "Forecasting workspace for ecommerce marketing teams." },
    ],
  }),
  component: AppLayout,
});

type NavItem = { to: string; label: string; icon: typeof BarChart3; exact?: boolean };
const NAV: NavItem[] = [
  { to: "/app", label: "Decision Center", icon: BarChart3, exact: true },
  { to: "/app/upload", label: "Data Upload", icon: Upload },
  { to: "/app/forecast", label: "Forecasting", icon: LineChart },
  { to: "/app/simulator", label: "Budget Simulator", icon: Calculator },
  { to: "/app/insights", label: "AI Insights", icon: Brain },
];

const WORKFLOW: Array<{
  key: WorkflowStep;
  label: string;
  to: string;
  result: string;
}> = [
  {
    key: "upload",
    label: "Upload",
    to: "/app/upload",
    result: "Load the confidential CSV or sample data.",
  },
  {
    key: "validate",
    label: "Validate",
    to: "/app/upload",
    result: "Confirm accepted rows and inspect row-level issues.",
  },
  {
    key: "forecast",
    label: "Forecast",
    to: "/app/forecast",
    result: "Compare downside, expected and upside planning cases by grain.",
  },
  {
    key: "simulate",
    label: "Simulate",
    to: "/app/simulator",
    result: "Allocate budget and inspect evidence-based support zones.",
  },
  {
    key: "explain",
    label: "Explain",
    to: "/app/insights",
    result: "Review statistical evidence, causal hypotheses and optional AI wording.",
  },
  {
    key: "export",
    label: "Export",
    to: "/app/insights",
    result: "Download the executive brief with limitations and next actions.",
  },
];

class RouteErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "2rem", textAlign: "center" }}>
          <p style={{ color: "var(--text-danger)", fontWeight: 500 }}>
            Something went wrong in this view.
          </p>
          <p style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
            {this.state.error?.message ?? "Unknown error"}
          </p>
          <button onClick={() => this.setState({ hasError: false, error: null })}>Try again</button>
        </div>
      );
    }
    return this.props.children;
  }
}

function AppLayout() {
  const { theme, toggle } = useTheme();
  const { isDemo, rows, workflow, loadDemo, clear, restartWorkflow } = useData();
  const loc = useLocation();
  const navigate = useNavigate();
  const [tourOpen, setTourOpen] = useState(false);
  const [tourStep, setTourStep] = useState(0);

  function openTour() {
    if (!rows.length) loadDemo();
    setTourStep(0);
    setTourOpen(true);
  }

  function restartJudgeWorkflow() {
    restartWorkflow();
    setTourStep(0);
    setTourOpen(true);
    void navigate({ to: "/app/upload" });
  }

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <Link to="/" className="flex items-center gap-2 px-6 py-5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-brand shadow-glow">
            <Sparkles className="h-4 w-4 text-primary-foreground" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">ForecastIQ</div>
            <div className="text-xs text-muted-foreground">Decision intelligence</div>
          </div>
        </Link>
        <nav className="flex-1 space-y-1 px-3 py-2">
          {NAV.map((n) => {
            const active = n.exact ? loc.pathname === n.to : loc.pathname.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
                }`}
              >
                <n.icon className="h-4 w-4" />
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-sidebar-border p-4 text-xs text-muted-foreground">
          <div className="flex items-center justify-between">
            <span>{rows.length.toLocaleString()} rows</span>
            {isDemo ? <Badge variant="secondary">Demo</Badge> : <Badge>Live</Badge>}
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background/80 px-6 backdrop-blur">
          <div className="flex items-center gap-3 md:hidden">
            <Link to="/" className="flex items-center gap-2">
              <div className="grid h-7 w-7 place-items-center rounded-md bg-gradient-brand">
                <Sparkles className="h-3.5 w-3.5 text-primary-foreground" />
              </div>
              <span className="text-sm font-semibold">ForecastIQ</span>
            </Link>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={openTour}
              className="rounded-md border border-border px-3 py-2 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
            >
              Show workflow
            </button>
            <button
              onClick={toggle}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              className="grid h-9 w-9 place-items-center rounded-md border border-border text-muted-foreground transition hover:bg-accent hover:text-foreground"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>
        {/* mobile nav */}
        <div className="flex gap-1 overflow-x-auto border-b border-border bg-background/80 px-2 py-2 md:hidden">
          {NAV.map((n) => {
            const active = n.exact ? loc.pathname === n.to : loc.pathname.startsWith(n.to);
            return (
              <Link
                key={n.to}
                to={n.to}
                className={`flex shrink-0 items-center gap-2 rounded-md px-3 py-1.5 text-xs ${
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground"
                }`}
              >
                <n.icon className="h-3.5 w-3.5" />
                {n.label}
              </Link>
            );
          })}
        </div>
        <div
          data-testid="workflow-controls"
          className="flex gap-2 overflow-x-auto border-b border-border bg-muted/30 px-3 py-2 sm:px-6"
          aria-label="Data and judge workflow controls"
        >
          <button
            type="button"
            onClick={loadDemo}
            className="min-h-10 shrink-0 rounded-md border border-border bg-background px-3 text-xs font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Sparkles className="mr-2 inline h-3.5 w-3.5" aria-hidden="true" />
            {isDemo ? "Reset demo" : "Load demo data"}
          </button>
          <button
            type="button"
            onClick={() => {
              clear();
              void navigate({ to: "/app/upload" });
            }}
            disabled={!rows.length}
            className="min-h-10 shrink-0 rounded-md border border-border bg-background px-3 text-xs font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="mr-2 inline h-3.5 w-3.5" aria-hidden="true" />
            Clear uploaded data
          </button>
          <button
            type="button"
            onClick={restartJudgeWorkflow}
            className="min-h-10 shrink-0 rounded-md border border-border bg-background px-3 text-xs font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <RotateCcw className="mr-2 inline h-3.5 w-3.5" aria-hidden="true" />
            Restart judge workflow
          </button>
        </div>
        <WorkflowIndicator workflow={workflow} pathname={loc.pathname} />
        <main className="flex-1 px-6 py-8">
          <RouteErrorBoundary>
            <Outlet />
          </RouteErrorBoundary>
        </main>
      </div>
      {tourOpen && (
        <JudgeTour step={tourStep} onStepChange={setTourStep} onClose={() => setTourOpen(false)} />
      )}
    </div>
  );
}

function WorkflowIndicator({
  workflow,
  pathname,
}: {
  workflow: Record<WorkflowStep, boolean>;
  pathname: string;
}) {
  return (
    <nav
      aria-label="Forecast workflow"
      className="border-b border-border bg-background/70 px-3 py-3 sm:px-6"
    >
      <ol className="flex gap-2 overflow-x-auto">
        {WORKFLOW.map((step, index) => {
          const active = pathname === step.to || pathname.startsWith(`${step.to}/`);
          return (
            <li key={step.key} className="min-w-0 flex-1 basis-28">
              <Link
                to={step.to}
                aria-current={active ? "step" : undefined}
                className={`flex min-w-[108px] items-center gap-2 rounded-md border px-2.5 py-2 text-xs ${
                  active
                    ? "border-primary/60 bg-primary/10 text-foreground"
                    : "border-border/50 text-muted-foreground hover:text-foreground"
                }`}
              >
                <span
                  className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] ${
                    workflow[step.key] ? "bg-success text-success-foreground" : "bg-muted"
                  }`}
                  aria-label={
                    workflow[step.key] ? `${step.label} complete` : `${step.label} pending`
                  }
                >
                  {workflow[step.key] ? <Check className="h-3 w-3" /> : index + 1}
                </span>
                <span>{step.label}</span>
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function JudgeTour({
  step,
  onStepChange,
  onClose,
}: {
  step: number;
  onStepChange: (step: number) => void;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const current = WORKFLOW[step];
  useEffect(() => {
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-background/80 p-4 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="judge-tour-title"
        className="w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-xl"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-primary">
              Judge tour · Step {step + 1} of {WORKFLOW.length}
            </div>
            <h2 id="judge-tour-title" className="mt-1 text-xl font-semibold">
              {current.label}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            aria-label="Skip judge tour"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center rounded-md border border-border text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{current.result}</p>
        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
          <div
            className="h-full bg-primary transition-[width]"
            style={{ width: `${((step + 1) / WORKFLOW.length) * 100}%` }}
          />
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <Link
            to={current.to}
            onClick={onClose}
            className="rounded-md border border-primary/50 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/10"
          >
            Open {current.label}
          </Link>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={step === 0}
              onClick={() => onStepChange(Math.max(0, step - 1))}
              className="inline-flex items-center rounded-md border border-border px-3 py-2 text-sm disabled:opacity-40"
            >
              <ChevronLeft className="mr-1 h-4 w-4" /> Back
            </button>
            {step < WORKFLOW.length - 1 ? (
              <button
                type="button"
                onClick={() => onStepChange(step + 1)}
                className="inline-flex items-center rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
              >
                Next <ChevronRight className="ml-1 h-4 w-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onStepChange(0)}
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
              >
                Restart tour
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
