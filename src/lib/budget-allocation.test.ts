import { describe, expect, it } from "vitest";
import { allocateBudgetExact, budgetTotal } from "./budget-allocation";

describe("allocateBudgetExact", () => {
  it("reconciles rounded allocations to the exact entered total", () => {
    const result = allocateBudgetExact(100.01, ["Google", "Meta", "Microsoft"], {
      Google: 1,
      Meta: 1,
      Microsoft: 1,
    });

    expect(result).toEqual({ Google: 33.34, Meta: 33.34, Microsoft: 33.33 });
    expect(budgetTotal(result)).toBe(100.01);
  });

  it("keeps a zero-history channel at zero when other evidence exists", () => {
    const result = allocateBudgetExact(1000, ["Google", "Meta", "Microsoft"], {
      Google: 3,
      Meta: 1,
      Microsoft: 0,
    });

    expect(result).toEqual({ Google: 750, Meta: 250, Microsoft: 0 });
    expect(budgetTotal(result)).toBe(1000);
  });

  it("falls back to an equal deterministic allocation when all history is zero", () => {
    const result = allocateBudgetExact(10, ["Google", "Meta", "Microsoft"], {});

    expect(result).toEqual({ Google: 3.34, Meta: 3.33, Microsoft: 3.33 });
    expect(budgetTotal(result)).toBe(10);
  });
});
