import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { CampaignRow } from "./types";
import type { DecisionSupportResponse } from "./backend-api";
import { generateDemoData } from "./demo-data";

interface DataCtx {
  rows: CampaignRow[];
  isDemo: boolean;
  setRows: (rows: CampaignRow[], demo?: boolean) => void;
  loadDemo: () => void;
  clear: () => void;
  workflow: WorkflowState;
  markWorkflow: (step: WorkflowStep) => void;
  planningSnapshot: PlanningSnapshot | null;
  setPlanningSnapshot: (snapshot: PlanningSnapshot) => void;
}

export type WorkflowStep = "upload" | "validate" | "forecast" | "simulate" | "explain" | "export";
export type WorkflowState = Record<WorkflowStep, boolean>;
export interface PlanningSnapshot {
  horizon: 30 | 60 | 90;
  allocationMode: "automatic" | "manual";
  budgets: Record<string, number>;
  decisionSupport: DecisionSupportResponse;
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
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const requestedDemo = localStorage.getItem(DEMO_REQUEST_KEY) === "1";
      if (requestedDemo) {
        setRowsState(generateDemoData(365));
        setIsDemo(true);
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
      } else {
        setRowsState(generateDemoData(365));
        setIsDemo(true);
        setWorkflow({ ...EMPTY_WORKFLOW, upload: true, validate: true });
      }
    } catch {
      setRowsState(generateDemoData(365));
      setWorkflow({ ...EMPTY_WORKFLOW, upload: true, validate: true });
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ rows, isDemo, workflow, planningSnapshot }),
      );
    } catch {
      // ignore quota
    }
  }, [rows, isDemo, workflow, planningSnapshot, hydrated]);

  const markWorkflow = useCallback((step: WorkflowStep) => {
    setWorkflow((current) => (current[step] ? current : { ...current, [step]: true }));
  }, []);
  const setPlanningSnapshot = useCallback((snapshot: PlanningSnapshot) => {
    setPlanningSnapshotState(snapshot);
  }, []);

  const value = useMemo<DataCtx>(
    () => ({
      rows,
      isDemo,
      setRows: (r, demo = false) => {
        setRowsState(r);
        setIsDemo(demo);
        setPlanningSnapshotState(null);
        setWorkflow((current) => ({ ...current, upload: r.length > 0 }));
      },
      loadDemo: () => {
        setRowsState(generateDemoData(365));
        setIsDemo(true);
        setPlanningSnapshotState(null);
        setWorkflow({ ...EMPTY_WORKFLOW, upload: true, validate: true });
        try {
          localStorage.removeItem(DEMO_REQUEST_KEY);
        } catch {
          // ignore storage availability
        }
      },
      clear: () => {
        setRowsState([]);
        setIsDemo(false);
        setWorkflow(EMPTY_WORKFLOW);
        setPlanningSnapshotState(null);
      },
      workflow,
      markWorkflow,
      planningSnapshot,
      setPlanningSnapshot,
    }),
    [rows, isDemo, workflow, markWorkflow, planningSnapshot, setPlanningSnapshot],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useData must be inside DataProvider");
  return ctx;
}
