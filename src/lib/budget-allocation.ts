export function allocateBudgetExact(
  totalBudget: number,
  channels: readonly string[],
  rawWeights: Record<string, number>,
): Record<string, number> {
  if (!channels.length) return {};
  const totalCents = Math.max(0, Math.round(finiteNumber(totalBudget) * 100));
  const weights = channels.map((channel) => Math.max(0, finiteNumber(rawWeights[channel])));
  const totalWeight = weights.reduce((sum, value) => sum + value, 0);
  const normalized = totalWeight > 0 ? weights : channels.map(() => 1);
  const denominator = normalized.reduce((sum, value) => sum + value, 0);
  const rawCents = normalized.map((weight) => (totalCents * weight) / denominator);
  const cents = rawCents.map(Math.floor);
  let remainder = totalCents - cents.reduce((sum, value) => sum + value, 0);
  const order = channels
    .map((_, index) => index)
    .sort((left, right) => {
      const fractionDelta = rawCents[right] - cents[right] - (rawCents[left] - cents[left]);
      return fractionDelta || left - right;
    });
  for (const index of order) {
    if (remainder <= 0) break;
    cents[index] += 1;
    remainder -= 1;
  }
  return Object.fromEntries(channels.map((channel, index) => [channel, cents[index] / 100]));
}

export function budgetTotal(budgets: Record<string, number>): number {
  return (
    Math.round(Object.values(budgets).reduce((sum, value) => sum + finiteNumber(value), 0) * 100) /
    100
  );
}

function finiteNumber(value: unknown): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}
