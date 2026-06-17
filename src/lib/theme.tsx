import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";
const Ctx = createContext<{ theme: Theme; toggle: () => void } | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");
  useEffect(() => {
    const stored = (typeof localStorage !== "undefined" &&
      localStorage.getItem("theme")) as Theme | null;
    const init = stored ?? "dark";
    setTheme(init);
    document.documentElement.classList.toggle("dark", init === "dark");
  }, []);
  return (
    <Ctx.Provider
      value={{
        theme,
        toggle: () => {
          const next = theme === "dark" ? "light" : "dark";
          setTheme(next);
          document.documentElement.classList.toggle("dark", next === "dark");
          try {
            localStorage.setItem("theme", next);
          } catch {
            // ignore
          }
        },
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be inside ThemeProvider");
  return ctx;
}
