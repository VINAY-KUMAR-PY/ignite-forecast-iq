import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { CampaignRow } from "./types";
import { generateDemoData } from "./demo-data";

interface DataCtx {
  rows: CampaignRow[];
  isDemo: boolean;
  setRows: (rows: CampaignRow[], demo?: boolean) => void;
  loadDemo: () => void;
  clear: () => void;
}

const Ctx = createContext<DataCtx | null>(null);

const STORAGE_KEY = "forecastiq:data:v1";

export function DataProvider({ children }: { children: ReactNode }) {
  const [rows, setRowsState] = useState<CampaignRow[]>([]);
  const [isDemo, setIsDemo] = useState(true);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setRowsState(parsed.rows);
        setIsDemo(parsed.isDemo);
      } else {
        setRowsState(generateDemoData(365));
        setIsDemo(true);
      }
    } catch {
      setRowsState(generateDemoData(365));
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ rows, isDemo }));
    } catch {
      // ignore quota
    }
  }, [rows, isDemo, hydrated]);

  const value = useMemo<DataCtx>(
    () => ({
      rows,
      isDemo,
      setRows: (r, demo = false) => {
        setRowsState(r);
        setIsDemo(demo);
      },
      loadDemo: () => {
        setRowsState(generateDemoData(365));
        setIsDemo(true);
      },
      clear: () => {
        setRowsState([]);
        setIsDemo(false);
      },
    }),
    [rows, isDemo],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useData must be inside DataProvider");
  return ctx;
}
