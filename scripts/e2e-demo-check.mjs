import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const CHROME_CANDIDATES = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
];

const chromePath = CHROME_CANDIDATES.find((candidate) => fs.existsSync(candidate));
const port = 9666 + Math.floor(Math.random() * 1000);
const userDataDir = path.join(os.tmpdir(), `forecastiq-e2e-${Date.now()}`);
const sampleCsv = path.resolve("data/sample_campaigns.csv");

if (!chromePath) {
  throw new Error("Chrome or Edge is required for the browser E2E smoke check.");
}

if (!fs.existsSync(sampleCsv)) {
  throw new Error(`Sample CSV not found at ${sampleCsv}`);
}

class Cdp {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = [];
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const pending = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) {
          pending.reject(
            new Error(`${message.error.message}: ${JSON.stringify(message.error.data || "")}`),
          );
        } else {
          pending.resolve(message.result);
        }
        return;
      }
      for (const listener of this.listeners) listener(message);
    });
  }

  async send(method, params = {}, sessionId, timeoutMs = 45000) {
    await this.ready;
    const id = this.nextId++;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    this.ws.send(JSON.stringify(payload));

    return await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timeout);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timeout);
          reject(error);
        },
      });
    });
  }

  on(listener) {
    this.listeners.push(listener);
  }

  close() {
    try {
      this.ws.close();
    } catch {
      // Browser is being torn down anyway.
    }
  }
}

async function waitForDevTools() {
  const url = `http://127.0.0.1:${port}/json/version`;
  for (let attempt = 0; attempt < 80; attempt++) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch {
      // Chrome is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Chrome DevTools endpoint did not start.");
}

async function evaluate(cdp, sessionId, expression, timeout = 30000) {
  const response = await cdp.send(
    "Runtime.evaluate",
    {
      expression,
      awaitPromise: true,
      returnByValue: true,
      timeout,
    },
    sessionId,
    timeout + 5000,
  );

  if (response.exceptionDetails) {
    throw new Error(`Evaluate failed: ${JSON.stringify(response.exceptionDetails)}`);
  }

  return response.result.value;
}

async function navigate(cdp, sessionId, url, waitMs) {
  await cdp.send("Page.navigate", { url }, sessionId);
  await waitUntil(
    cdp,
    sessionId,
    `document.readyState === "interactive" || document.readyState === "complete"`,
    Math.max(8000, waitMs),
  );
  await delay(Math.min(waitMs, 1000));
}

async function waitUntil(cdp, sessionId, expression, timeoutMs = 30000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const matched = await evaluate(cdp, sessionId, `Boolean(${expression})`, 4000);
      if (matched) return true;
    } catch (error) {
      lastError = error;
    }
    await delay(intervalMs);
  }
  if (lastError) return false;
  return false;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function uniqueClean(values) {
  return [...new Set(values)].filter(Boolean).filter((value) => !value.includes("favicon"));
}

let chrome;
const result = { ok: false, sampleCsv };
const consoleErrors = [];
const networkFailures = [];
const runtimeExceptions = [];
const apiResponses = [];
const requestUrls = new Map();

try {
  chrome = spawn(
    chromePath,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "ignore"] },
  );

  const version = await waitForDevTools();
  const cdp = new Cdp(version.webSocketDebuggerUrl);
  await cdp.ready;

  const target = await cdp.send("Target.createTarget", { url: "about:blank" });
  const attached = await cdp.send("Target.attachToTarget", {
    targetId: target.targetId,
    flatten: true,
  });
  const sessionId = attached.sessionId;

  cdp.on((message) => {
    if (message.sessionId !== sessionId) return;

    if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
      consoleErrors.push(
        message.params.args.map((arg) => arg.value || arg.description || "").join(" "),
      );
    }

    if (message.method === "Runtime.exceptionThrown") {
      runtimeExceptions.push(
        message.params.exceptionDetails?.text ||
          message.params.exceptionDetails?.exception?.description ||
          "Runtime exception",
      );
    }

    if (message.method === "Network.requestWillBeSent") {
      requestUrls.set(message.params.requestId, message.params.request.url);
    }

    if (message.method === "Network.responseReceived") {
      const url = message.params.response.url || "";
      if (url.includes("/api/")) {
        apiResponses.push(`${message.params.response.status} ${url}`);
      }
    }

    if (message.method === "Network.loadingFailed") {
      const url = requestUrls.get(message.params.requestId) || "";
      if (url.includes("favicon") || message.params.errorText === "net::ERR_ABORTED") return;
      networkFailures.push(
        `${url} ${message.params.errorText || ""} ${message.params.blockedReason || ""}`.trim(),
      );
    }

    if (message.method === "Log.entryAdded" && message.params.entry.level === "error") {
      consoleErrors.push(message.params.entry.text || "");
    }
  });

  for (const method of [
    "Page.enable",
    "Runtime.enable",
    "Network.enable",
    "Log.enable",
    "DOM.enable",
  ]) {
    await cdp.send(method, {}, sessionId);
  }

  const base = "http://127.0.0.1:5173";

  await navigate(cdp, sessionId, `${base}/app/upload`, 1500);
  await waitUntil(cdp, sessionId, `document.querySelector('input[type="file"]')`, 15000);
  const doc = await cdp.send("DOM.getDocument", { depth: -1, pierce: true }, sessionId);
  const input = await cdp.send(
    "DOM.querySelector",
    { nodeId: doc.root.nodeId, selector: 'input[type="file"]' },
    sessionId,
  );
  if (!input.nodeId) throw new Error("Upload input not found");

  await cdp.send("DOM.setFileInputFiles", { nodeId: input.nodeId, files: [sampleCsv] }, sessionId);
  await waitUntil(
    cdp,
    sessionId,
    `(document.body.innerText || "").includes("Uploaded dataset") &&
      ((document.body.innerText || "").includes("1,440") || (document.body.innerText || "").includes("1440"))`,
    30000,
  );
  result.upload = await evaluate(
    cdp,
    sessionId,
    `(() => {
      const text = document.body.innerText || "";
      const issueValue = document
        .querySelector('[data-testid="issues-detected-value"]')
        ?.textContent?.trim();
      return {
        title: document.title,
        loadedSampleRows: text.includes("1,440") || text.includes("1440"),
        uploadedDataset: text.includes("Uploaded dataset"),
        issuesDetectedZero: issueValue === "0",
        hasPreview: text.includes("Data preview") && text.includes("Brand Search")
      };
    })()`,
  );

  await navigate(cdp, sessionId, `${base}/app/forecast`, 1500);
  await waitUntil(
    cdp,
    sessionId,
    `(document.body.innerText || "").includes("Revenue forecast") &&
      (document.body.innerText || "").includes("ROAS forecast")`,
    30000,
  );
  await waitUntil(
    cdp,
    sessionId,
    `document.querySelector('[data-testid="model-diagnostics"]') ||
      document.querySelector('[data-testid="accuracy-dashboard"]') ||
      (document.body.innerText || "").includes("Backend unavailable")`,
    60000,
  );
  result.forecast = await evaluate(
    cdp,
    sessionId,
    `(() => {
      const text = document.body.innerText || "";
      return {
        title: document.title,
        hasRevenueForecast: text.includes("Revenue forecast"),
        hasRoasForecast: text.includes("ROAS forecast"),
        hasConfidenceIntervals: text.includes("95% CI") || text.includes("confidence"),
        hasDiagnostics: Boolean(document.querySelector('[data-testid="model-diagnostics"]')),
        hasAccuracyDashboard: Boolean(document.querySelector('[data-testid="accuracy-dashboard"]')),
        hasExplainabilityCenter: Boolean(document.querySelector('[data-testid="explainability-center"]')),
        hasConfidenceOverview: Boolean(document.querySelector('[data-testid="confidence-intervals"]')),
        hasExecutiveBrief: Boolean(document.querySelector('[data-testid="executive-business-brief"]')),
        backendFallbackWarning: text.includes("Backend unavailable")
      };
    })()`,
  );

  await navigate(cdp, sessionId, `${base}/app/simulator`, 1500);
  await waitUntil(
    cdp,
    sessionId,
    `document.querySelector('[data-testid="channel-breakdown"]') &&
      document.querySelector('[data-testid="decision-support"]') &&
      (document.body.innerText || "").includes("Projected revenue")`,
    60000,
  );
  result.simulator = await evaluate(
    cdp,
    sessionId,
    `(() => {
      const text = document.body.innerText || "";
      return {
        title: document.title,
        hasChannelBudgets: text.includes("Channel budgets"),
        hasProjectedRevenue: text.includes("Projected revenue"),
        hasChannels: ["Google Ads", "Meta Ads", "Microsoft Ads"].every((name) => text.includes(name)),
        hasBreakdown: Boolean(document.querySelector('[data-testid="channel-breakdown"]')),
        hasOptimizer: Boolean(document.querySelector('[data-testid="ai-budget-optimizer"]')),
        hasWhatIf: Boolean(document.querySelector('[data-testid="what-if-engine"]')),
        hasRiskEngine: Boolean(document.querySelector('[data-testid="risk-detection"]')),
        hasOpportunityEngine: Boolean(document.querySelector('[data-testid="opportunity-detection"]')),
        hasHealthScore: Boolean(document.querySelector('[data-testid="channel-health"]'))
      };
    })()`,
  );

  await navigate(cdp, sessionId, `${base}/app/insights`, 1500);
  await waitUntil(
    cdp,
    sessionId,
    `Array.from(document.querySelectorAll("button")).some((el) =>
      el.innerText.includes("Generate insights") || el.innerText.includes("Regenerate"))`,
    30000,
  );
  result.insightsButtonClicked = await evaluate(
    cdp,
    sessionId,
    `(() => {
      const button = Array.from(document.querySelectorAll("button")).find((el) =>
        el.innerText.includes("Generate insights") || el.innerText.includes("Regenerate")
      );
      if (!button) return false;
      button.click();
      return true;
    })()`,
  );
  await waitUntil(
    cdp,
    sessionId,
    `(document.body.innerText || "").toLowerCase().includes("executive summary") &&
      (document.body.innerText || "").toLowerCase().includes("action plan")`,
    60000,
  );
  result.insights = await evaluate(
    cdp,
    sessionId,
    `(() => {
      const text = document.body.innerText || "";
      const normalized = text.toLowerCase();
      return {
        title: document.title,
        hasExecutiveSummary: normalized.includes("executive summary"),
        hasRevenueDrivers: normalized.includes("revenue drivers"),
        hasRiskAnalysis: normalized.includes("risk analysis"),
        hasActionPlan: normalized.includes("action plan")
      };
    })()`,
  );

  result.consoleErrors = uniqueClean(consoleErrors);
  result.networkFailures = uniqueClean(networkFailures);
  result.runtimeExceptions = uniqueClean(runtimeExceptions);
  result.apiResponses = uniqueClean(apiResponses);

  result.ok =
    Object.values(result.upload).every(Boolean) &&
    result.forecast.hasRevenueForecast &&
    result.forecast.hasRoasForecast &&
    result.forecast.hasConfidenceIntervals &&
    result.forecast.hasDiagnostics &&
    result.forecast.hasAccuracyDashboard &&
    result.forecast.hasExplainabilityCenter &&
    result.forecast.hasConfidenceOverview &&
    result.forecast.hasExecutiveBrief &&
    !result.forecast.backendFallbackWarning &&
    Object.values(result.simulator).every(Boolean) &&
    result.insightsButtonClicked &&
    Object.values(result.insights).every(Boolean) &&
    result.consoleErrors.length === 0 &&
    result.networkFailures.length === 0 &&
    result.runtimeExceptions.length === 0;

  cdp.close();
} catch (error) {
  result.error = error?.stack || String(error);
  result.consoleErrors = uniqueClean(consoleErrors);
  result.networkFailures = uniqueClean(networkFailures);
  result.runtimeExceptions = uniqueClean(runtimeExceptions);
  result.apiResponses = uniqueClean(apiResponses);
} finally {
  if (chrome && !chrome.killed) chrome.kill("SIGKILL");
  try {
    fs.rmSync(userDataDir, { recursive: true, force: true });
  } catch {
    // Windows can hold temporary Chrome files briefly; they are safe to ignore.
  }
}

console.log(JSON.stringify(result, null, 2));
process.exit(result.ok ? 0 : 1);
