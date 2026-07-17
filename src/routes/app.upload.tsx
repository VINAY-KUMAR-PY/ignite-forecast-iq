import { createFileRoute } from "@tanstack/react-router";
import { useRef, useState, type KeyboardEvent } from "react";
import { AlertCircle, CheckCircle2, Download, FileUp, PlayCircle, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DataReadinessScoreCard } from "@/components/data-readiness-score";
import { parseCSV, toCSV } from "@/lib/csv";
import { useData } from "@/lib/data-store";
import { generateDemoData } from "@/lib/demo-data";
import { validateRowsApi } from "@/lib/backend-api";
import type { ValidationResult } from "@/lib/types";

export const Route = createFileRoute("/app/upload")({
  head: () => ({ meta: [{ title: "Data upload · ForecastIQ" }] }),
  component: UploadPage,
});

export function UploadPage() {
  const { setRows, loadDemo, rows, isDemo, markWorkflow } = useData();
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (!files.length) return;
    const parsedFiles = await Promise.all(
      files.map(async (file, sourceIndex) => ({
        file,
        sourceIndex,
        parsed: parseCSV(await file.text()),
      })),
    );
    let rowOffset = 0;
    const browserIssues = parsedFiles.flatMap(({ parsed, file }) => {
      const adjusted = parsed.issues.map((issue) => ({
        ...issue,
        row: issue.row > 1 ? issue.row + rowOffset : issue.row,
        message: files.length > 1 ? `${file.name}: ${issue.message}` : issue.message,
      }));
      rowOffset += parsed.totalRows;
      return adjusted;
    });
    const browserRows = parsedFiles.flatMap(({ parsed }) => parsed.rows);
    const totalRows = parsedFiles.reduce((sum, { parsed }) => sum + parsed.totalRows, 0);
    const rawRows = parsedFiles.flatMap(({ parsed, file, sourceIndex }) =>
      parsed.rawRows.map((row) => ({
        ...row,
        __source_file_id: `source-${sourceIndex + 1}`,
        __source_file_name: file.name,
      })),
    );
    let finalResult: ValidationResult = {
      rows: browserRows,
      issues: browserIssues,
      totalRows,
      validRows: browserRows.length,
    };
    try {
      const backendResult = await validateRowsApi(rawRows);
      finalResult = {
        ...backendResult,
        issues: uniqueIssues([...browserIssues, ...backendResult.issues]),
        totalRows,
      };
    } catch {
      toast.warning(
        "Backend validation unavailable; using browser validation without a readiness score",
      );
    }
    setResult(finalResult);
    if (finalResult.rows.length > 0) {
      setRows(finalResult.rows, false, finalResult.dataReadiness ?? null);
      markWorkflow("validate");
      toast.success(
        `Imported ${finalResult.rows.length.toLocaleString()} rows from ${files.length} file${files.length === 1 ? "" : "s"}`,
      );
    } else {
      toast.error("No valid rows found in file");
    }
  }

  function openFilePicker() {
    inputRef.current?.click();
  }

  function handleDropzoneKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openFilePicker();
    }
  }

  function downloadDemo() {
    const csv = toCSV(generateDemoData(365));
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "forecastiq-demo.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const issueCounts = result
    ? result.issues.reduce<Record<string, number>>((acc, i) => {
        acc[i.type] = (acc[i.type] ?? 0) + 1;
        return acc;
      }, {})
    : {};

  return (
    <>
      <PageHeader
        title="Data upload"
        description="Upload campaign, GA4, Shopify, or ads CSV data. ForecastIQ normalizes common ecommerce exports before validation."
        actions={
          <>
            <Button variant="outline" onClick={downloadDemo}>
              <Download className="mr-2 h-4 w-4" /> Sample CSV
            </Button>
            <Button
              variant="hero"
              onClick={() => {
                loadDemo();
                toast.success("Demo data reloaded");
              }}
            >
              <RotateCcw className="mr-2 h-4 w-4" /> Load sample data
            </Button>
          </>
        }
      />

      <Card
        data-testid="judge-demo-path"
        className="mb-6 min-w-0 border-primary/20 bg-primary/5 p-5"
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <PlayCircle className="h-4 w-4 text-primary" /> Judge demo path
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              Load sample data, open the Executive Decision Center, then run the Forecast, Budget
              Simulator, and AI Insights. This gives judges the full story in under two minutes.
            </p>
          </div>
          <div className="flex min-w-0 flex-wrap gap-2">
            <Button
              variant="hero"
              onClick={() => {
                loadDemo();
                toast.success("Sample data loaded for judge demo");
              }}
            >
              <RotateCcw className="mr-2 h-4 w-4" /> Load sample data
            </Button>
            <Button variant="outline" onClick={downloadDemo}>
              <Download className="mr-2 h-4 w-4" /> Download CSV
            </Button>
          </div>
        </div>
      </Card>

      <Card
        className={`bg-gradient-card min-w-0 border-2 border-dashed p-6 text-center transition sm:p-10 ${
          dragging ? "border-primary bg-accent/30" : "border-border/60"
        }`}
        role="button"
        tabIndex={0}
        aria-label="Upload CSV drop target. Press Enter or Space to choose a campaign data file."
        onKeyDown={handleDropzoneKeyDown}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files);
        }}
      >
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-gradient-brand shadow-glow">
          <FileUp className="h-5 w-5 text-primary-foreground" />
        </div>
        <h3 className="mt-4 text-lg font-semibold">Drop your CSV here</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Drop one or more ecommerce exports: GA4 sessionSource/sessionMedium/purchaseRevenue,
          Shopify created_at/total_price/orders, Ads spend/clicks/impressions/conversion_value, or
          the ForecastIQ sample format.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) void handleFiles(e.target.files);
          }}
        />
        <Button variant="hero" className="mt-6" onClick={openFilePicker}>
          Choose file(s)
        </Button>
        <p className="mt-2 text-[13px] text-muted-foreground">
          Need sample data?{" "}
          <a
            href="/data/sample_campaigns.csv"
            download="sample_campaigns.csv"
            className="text-primary underline-offset-4 hover:underline"
          >
            Download sample CSV
          </a>
        </p>
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card className="bg-gradient-card border-border/60 min-w-0 p-4">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Loaded rows</div>
          <div className="mt-1 text-2xl font-bold">{rows.length.toLocaleString()}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {isDemo ? "Demo dataset" : "Uploaded dataset"}
          </div>
        </Card>
        <Card className="bg-gradient-card border-border/60 min-w-0 p-4">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">
            Last import — valid
          </div>
          <div className="mt-1 text-2xl font-bold text-success">{result?.validRows ?? "—"}</div>
          <div className="mt-1 text-xs text-muted-foreground">
            of {result?.totalRows ?? "—"} parsed
          </div>
        </Card>
        <Card className="bg-gradient-card border-border/60 min-w-0 p-4">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">
            Issues detected
          </div>
          <div data-testid="issues-detected-value" className="mt-1 text-2xl font-bold text-warning">
            {result?.issues.length ?? 0}
          </div>
          <div className="mt-1 flex flex-wrap gap-1 text-xs">
            {Object.entries(issueCounts).map(([t, c]) => (
              <Badge key={t} variant="secondary" className="capitalize">
                {t.replace("_", " ")}: {c}
              </Badge>
            ))}
          </div>
        </Card>
      </div>

      {result && (
        <div className="mt-6">
          <DataReadinessScoreCard
            score={result.dataReadiness ?? null}
            status={result.dataReadiness ? "available" : "unavailable"}
            error="The backend readiness assessment could not be completed."
            context="upload"
          />
        </div>
      )}

      {result && (
        <Card className="mt-6 min-w-0 border-border/60 bg-gradient-card p-5">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Validation details
          </div>
          {result.issues.length > 0 ? (
            <>
              <div className="mt-3 flex items-center gap-2 text-sm font-semibold text-warning">
                <AlertCircle className="h-4 w-4" /> {result.issues.length} validation issues
              </div>
              <div className="mt-3 max-h-[200px] overflow-x-auto overflow-y-auto rounded-md border border-border/60 bg-background/50">
                <table className="min-w-[520px] w-full text-xs">
                  <thead className="sticky top-0 bg-muted/50">
                    <tr>
                      <th className="px-3 py-2 text-left">Row</th>
                      <th className="px-3 py-2 text-left">Type</th>
                      <th className="px-3 py-2 text-left">Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.issues.map((issue, idx) => {
                      const severity = getIssueSeverity(issue.type);
                      return (
                        <tr
                          key={`${issue.row}-${issue.type}-${idx}`}
                          className="border-t border-border/40"
                        >
                          <td className="px-3 py-1.5">{issue.row}</td>
                          <td className="px-3 py-1.5">
                            <Badge
                              variant={severity === "error" ? "destructive" : "outline"}
                              className={
                                severity === "warning"
                                  ? "border-warning/50 bg-warning/10 text-warning"
                                  : "capitalize"
                              }
                            >
                              {issue.type.replace("_", " ")}
                            </Badge>
                          </td>
                          <td className="px-3 py-1.5 text-muted-foreground">{issue.message}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="mt-3 flex items-center gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
              <CheckCircle2 className="h-4 w-4" /> All rows passed validation.
            </div>
          )}
        </Card>
      )}

      {rows.length > 0 && (
        <Card className="mt-6 bg-gradient-card border-border/60 min-w-0 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CheckCircle2 className="h-4 w-4 text-success" /> Data preview (first 20 rows)
          </div>
          <div className="mt-3 max-h-96 overflow-auto rounded-md border border-border/60">
            <table className="min-w-[860px] w-full text-xs">
              <thead className="sticky top-0 bg-muted/50">
                <tr>
                  {[
                    "date",
                    "channel",
                    "campaign_type",
                    "campaign_name",
                    "spend",
                    "clicks",
                    "impressions",
                    "conversions",
                    "revenue",
                    "roas",
                  ].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium capitalize">
                      {h.replace("_", " ")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 20).map((r, i) => (
                  <tr key={i} className="border-t border-border/40">
                    <td className="px-3 py-1.5">{r.date}</td>
                    <td className="px-3 py-1.5">{r.channel}</td>
                    <td className="px-3 py-1.5">{r.campaign_type}</td>
                    <td className="px-3 py-1.5">{r.campaign_name}</td>
                    <td className="px-3 py-1.5">${r.spend.toFixed(2)}</td>
                    <td className="px-3 py-1.5">{r.clicks}</td>
                    <td className="px-3 py-1.5">{r.impressions}</td>
                    <td className="px-3 py-1.5">{r.conversions}</td>
                    <td className="px-3 py-1.5">${r.revenue.toFixed(2)}</td>
                    <td className="px-3 py-1.5">{r.roas.toFixed(2)}x</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}

function getIssueSeverity(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes("warning") || normalized === "duplicate") return "warning";
  return "error";
}

function uniqueIssues(issues: ValidationResult["issues"]) {
  return Array.from(
    new Map(issues.map((issue) => [`${issue.row}|${issue.type}|${issue.message}`, issue])).values(),
  );
}
