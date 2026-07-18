import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { CampaignRow, DataReadinessScore } from "./types";
import {
  validateRowsApi,
  type DecisionSupportResponse,
  type ForecastApiResponse,
} from "./backend-api";
import { generateDemoData } from "./demo-data";

interface DataCtx {
  rows: CampaignRow[];
  isDemo: boolean;
  setRows: (rows: CampaignRow[], demo?: boolean, readiness?: DataReadinessScore | null) => void;
  loadDemo: () => void;
  clear: () => void;
  restartWorkflow: () => void;
  dataReadiness: DataReadinessScore | null;
  readinessStatus: ReadinessStatus;
  readinessError: string | null;
  ensureDataReadiness: (force?: boolean) => Promise<void>;
  workflow: WorkflowState;
  markWorkflow: (step: WorkflowStep) => void;
  planningSnapshot: PlanningSnapshot | null;
  setPlanningSnapshot: (snapshot: PlanningSnapshot) => void;
  forecastSnapshot: ForecastSnapshot | null;
  setForecastSnapshot: (snapshot: ForecastSnapshot) => void;
}

export type WorkflowStep = "upload" | "validate" | "forecast" | "simulate" | "explain" | "export";
export type WorkflowState = Record<WorkflowStep, boolean>;
export type ReadinessStatus = "idle" | "loading" | "available" | "unavailable";
export interface PlanningSnapshot {
  horizon: 30 | 60 | 90;
  allocationMode: "automatic" | "manual";
  budgets: Record<string, number>;
  decisionSupport: DecisionSupportResponse;
}

export interface ForecastSnapshot {
  horizon: 30 | 60 | 90;
  level: "overall" | "channel" | "campaign_type" | "campaign";
  value?: string;
  response: ForecastApiResponse;
}

const EMPTY_WORKFLOW: WorkflowState = {
  upload: false,
  validate: false,
  forecast: false,
  simulate: false,
  explain: false,
  export: false,
};

const Ctx = createContext<DataCtx | null>(null);

const STORAGE_KEY = "forecastiq:data:v1";
export const DEMO_REQUEST_KEY = "forecastiq:demo-requested";

export function DataProvider({ children }: { children: ReactNode }) {
  const [rows, setRowsState] = useState<CampaignRow[]>([]);
  const [isDemo, setIsDemo] = useState(true);
  const [workflow, setWorkflow] = useState<WorkflowState>(EMPTY_WORKFLOW);
  const [planningSnapshot, setPlanningSnapshotState] = useState<PlanningSnapshot | null>(null);
  const [forecastSnapshot, setForecastSnapshotState] = useState<ForecastSnapshot | null>(null);
  const [dataReadiness, setDataReadiness] = useState<DataReadinessScore | null>(null);
  const [readinessStatus, setReadinessStatus] = useState<ReadinessStatus>("idle");
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const readinessRequestRef = useRef<Promise<void> | null>(null);
  const readinessRequestIdRef = useRef(0);

  useEffect(() => {
    try {
      const requestedDemo = localStorage.getItem(DEMO_REQUEST_KEY) === "1";
      if (requestedDemo) {
        setRowsState(generateDemoData(365));
        setIsDemo(true);
        setDataReadiness(null);
        setReadinessStatus("idle");
        setWorkflow({ ...EMPTY_WORKFLOW, upload: true, validate: true });
        localStorage.removeItem(DEMO_REQUEST_KEY);
        setHydrated(true);
        return;
      }

      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setRowsState(parsed.rows);
        setIsDemo(parsed.isDemo);
        setWorkflow({
          ...EMPTY_WORKFLOW,
          upload: Boolean(parsed.rows?.length),
          validate: Boolean(parsed.rows?.length),
          ...(parsed.workflow ?? {}),
        });
        setPlanningSnapshotState(parsed.planningSnapshot ?? null);
        setForecastSnapshotState(parsed.forecastSnapshot ?? null);
        setDataReadiness(parsed.dataReadiness ?? null);
        setReadinessStatus(parsed.dataReadiness ? "available" : "idle");
      } else {
        setRowsState(generateDemoData(365));
        setIsDemo(true);
        setDataReadiness(null);
        setReadinessStatus("idle");
        setWorkflow({ ...EMPTY_WORKFLOW, upload: true, validate: true });
      }
    } catch {
      setRowsState(generateDemoData(365));
      setDataReadiness(null);
      setReadinessStatus("idle");
      setWorkflow({ ...EMPTY_WORKFLOW, upload: true, validate: true });
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          rows,
          isDemo,
          workflow,
          planningSnapshot,
          forecastSnapshot,
          dataReadiness,
        }),
      );
    } catch {
      // ignore quota
    }
  }, [rows, isDemo, workflow, planningSnapshot, forecastSnapshot, dataReadiness, hydrated]);

  const markWorkflow = useCallback((step: WorkflowStep) => {
    setWorkflow((current) => (current[step] ? current : { ...current, [step]: true }));
  }, []);
  const setPlanningSnapshot = useCallback((snapshot: PlanningSnapshot) => {
    setPlanningSnapshotState(snapshot);
  }, []);
  const setForecastSnapshot = useCallback((snapshot: ForecastSnapshot) => {
    setForecastSnapshotState(snapshot);
  }, []);

  const ensureDataReadiness = useCallback(
    async (force = false) => {
      if (!rows.length) return;
      if (!force && dataReadiness) return;
      if (!force && readinessRequestRef.current) return readinessRequestRef.current;

      const requestId = ++readinessRequestIdRef.current;
      setReadinessStatus("loading");
      setReadinessError(null);
      const request = validateRowsApi(rows)
        .then((response) => {
          if (requestId !== readinessRequestIdRef.current) return;
          if (!response.dataReadiness) {
            setDataReadiness(null);
            setReadinessStatus("unavailable");
            setReadinessError("The validation service did not return a readiness assessment.");
            return;
          }
          setDataReadiness(response.dataReadiness);
          setReadinessStatus("available");
        })
        .catch((error: Error) => {
          if (requestId !== readinessRequestIdRef.current) return;
          setDataReadiness(null);
          setReadinessStatus("unavailable");
          setReadinessError(error.message || "The validation service is unavailable.");
        })
        .finally(() => {
          if (requestId === readinessRequestIdRef.current) readinessRequestRef.current = null;
        });
      readinessRequestRef.current = request;
      return request;
    },
    [rows, dataReadiness],
  );

  const value = useMemo<DataCtx>(
    () => ({
      rows,
      isDemo,
      setRows: (r, demo = false, readiness = null) => {
        readinessRequestIdRef.current += 1;
        readinessRequestRef.current = null;
        setRowsState(r);
        setIsDemo(demo);
        setDataReadiness(readiness);
        setReadinessStatus(readiness ? "available" : "idle");
        setReadinessError(null);
        setPlanningSnapshotState(null);
        setForecastSnapshotState(null);
        setWorkflow((current) => ({ ...current, upload: r.length > 0 }));
      },
      loadDemo: () => {
        readinessRequestIdRef.current += 1;
        readinessRequestRef.current = null;
        setRowsState(generateDemoData(365));
        setIsDemo(true);
        setDataReadiness(null);
        setReadinessStatus("idle");
        setReadinessError(null);
        setPlanningSnapshotState(null);
        setForecastSnapshotState(null);
        setWorkflow({ ...EMPTY_WORKFLOW, upload: true, validate: true });
        try {
          localStorage.removeItem(DEMO_REQUEST_KEY);
        } catch {
          // ignore storage availability
        }
      },
      clear: () => {
        readinessRequestIdRef.current += 1;
        readinessRequestRef.current = null;
        setRowsState([]);
        setIsDemo(false);
        setDataReadiness(null);
        setReadinessStatus("idle");
        setReadinessError(null);
        setWorkflow(EMPTY_WORKFLOW);
        setPlanningSnapshotState(null);
        setForecastSnapshotState(null);
      },
      restartWorkflow: () => {
        setWorkflow({ ...EMPTY_WORKFLOW, upload: rows.length > 0, validate: rows.length > 0 });
        setPlanningSnapshotState(null);
        setForecastSnapshotState(null);
      },
      dataReadiness,
      readinessStatus,
      readinessError,
      ensureDataReadiness,
      workflow,
      markWorkflow,
      planningSnapshot,
      setPlanningSnapshot,
      forecastSnapshot,
      setForecastSnapshot,
    }),
    [
      rows,
      isDemo,
      workflow,
      markWorkflow,
      planningSnapshot,
      setPlanningSnapshot,
      forecastSnapshot,
      setForecastSnapshot,
      dataReadiness,
      readinessStatus,
      readinessError,
      ensureDataReadiness,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useData must be inside DataProvider");
  return ctx;
}
