import React from "react";
import { createFileRoute, Link, Outlet, useLocation } from "@tanstack/react-router";
import { BarChart3, Brain, Calculator, LineChart, Moon, Sparkles, Sun, Upload } from "lucide-react";
import { useTheme } from "@/lib/theme";
import { useData } from "@/lib/data-store";
import { Badge } from "@/components/ui/badge";

export const Route = createFileRoute("/app")({
  head: () => ({
    meta: [
      { title: "Decision Center - AIgnition ForecastIQ" },
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
  const { isDemo, rows } = useData();
  const loc = useLocation();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <Link to="/" className="flex items-center gap-2 px-6 py-5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-brand shadow-glow">
            <Sparkles className="h-4 w-4 text-primary-foreground" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold">AIgnition</div>
            <div className="text-xs text-muted-foreground">ForecastIQ</div>
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
              onClick={toggle}
              aria-label="Toggle theme"
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
        <main className="flex-1 px-6 py-8">
          <RouteErrorBoundary>
            <Outlet />
          </RouteErrorBoundary>
        </main>
      </div>
    </div>
  );
}
