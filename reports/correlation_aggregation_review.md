# Correlation-Aware Aggregate Interval Review

Date: 2026-07-17

## Decision

Not adopted. ForecastIQ keeps the existing conservative aggregate planning
ranges for this submission.

## Evidence Reviewed

`reports/backtest_report.json` records horizon-level residual standard
deviations and rolling-origin coverage/width summaries. It does not retain a
paired matrix of channel residual observations aligned by holdout date and
fold. Those pairs are required to estimate cross-channel covariance without
leakage.

## Method Considered

The proposed experiment would align held-out channel residuals by fold/date,
estimate a covariance matrix, shrink it toward a diagonal target, project it to
positive semidefinite form, and compare the aggregate interval with the current
method on empirical coverage, width, calibration error, sample size, and
stability by horizon.

## Why It Was Rejected

- Aggregate residual standard deviations cannot identify channel correlation.
- Reconstructing pseudo-pairs from summary metrics would manufacture evidence.
- Narrower intervals without a leak-free coverage comparison could create
  dangerous undercoverage.
- The 90-day backtest has fewer evaluation windows, making covariance estimates
  especially unstable.

## Follow-Up Gate

Adopt only after the backtest emits paired held-out residuals and the method
maintains practical coverage across every horizon with stable shrinkage and a
positive-semidefinite covariance matrix. Until then, no evaluator or product
forecast behavior changes.
