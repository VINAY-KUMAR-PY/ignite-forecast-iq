import { Link } from "@tanstack/react-router";
import { Database } from "lucide-react";
import { Button } from "./ui/button";
import { useData } from "@/lib/data-store";

export function EmptyState() {
  const { loadDemo } = useData();
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/40 px-6 py-20 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-brand shadow-glow">
        <Database className="h-5 w-5 text-primary-foreground" />
      </div>
      <h2 className="mt-4 text-xl font-semibold">No campaign data yet</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Load demo data to explore ForecastIQ or upload your own CSV with campaign performance.
      </p>
      <div className="mt-6 flex gap-3">
        <Button variant="hero" onClick={loadDemo}>
          Load demo data
        </Button>
        <Link to="/app/upload">
          <Button variant="outline">Upload CSV</Button>
        </Link>
      </div>
    </div>
  );
}
