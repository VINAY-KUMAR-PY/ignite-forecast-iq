import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { MODEL_PATH_CONFIDENCE } from "@/lib/model-validation.generated";

export function ModelPathConfidenceBadge() {
  return (
    <Card data-testid="model-path-confidence" className="mb-6 border-primary/20 bg-primary/5 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="text-sm font-semibold">Live/offline model confidence</div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            ForecastIQ uses a richer live dashboard model and a compact offline evaluator artifact.
            Backtest evidence keeps the paths directionally reconciled for planning decisions.
          </p>
        </div>
        <Badge variant="outline" className="w-fit shrink-0 border-primary/40 text-primary">
          {MODEL_PATH_CONFIDENCE.label}
        </Badge>
      </div>
    </Card>
  );
}
