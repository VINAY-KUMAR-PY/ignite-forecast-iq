# Budget Elasticity Validation

Generated: 2026-07-04T03:28:31.095206+00:00

## Method

For each channel, ForecastIQ compares adjacent monthly periods where spend changed by at least 15%. The prior month's revenue is multiplied by `spend_response_multiplier(current_spend / previous_spend)`, then compared with observed revenue.

## Results

- Cases evaluated: 12
- Revenue response MAE: $10,066.39
- Revenue response MAPE: 9.49%
- Direction accuracy: 100.00%

| Channel | Month | Spend change | Actual revenue | Predicted revenue | Abs. error | Direction match |
|---|---:|---:|---:|---:|---:|---|
| Google Ads | 2025-09 | 243.33% | $183,251.97 | $152,632.66 | $30,619.31 | True |
| Google Ads | 2025-10 | 19.15% | $222,271.66 | $218,348.86 | $3,922.80 | True |
| Google Ads | 2026-03 | 21.53% | $264,827.13 | $266,965.23 | $2,138.10 | True |
| Google Ads | 2026-06 | -46.04% | $147,594.38 | $179,290.54 | $31,696.16 | True |
| Meta Ads | 2025-09 | 238.06% | $100,653.27 | $81,314.17 | $19,339.10 | True |
| Meta Ads | 2025-10 | 16.88% | $117,455.87 | $117,646.53 | $190.66 | True |
| Meta Ads | 2026-03 | 19.73% | $134,838.92 | $139,159.08 | $4,320.16 | True |
| Meta Ads | 2026-06 | -45.04% | $79,808.36 | $93,045.72 | $13,237.36 | True |
| Microsoft Ads | 2025-09 | 240.56% | $49,581.73 | $41,767.83 | $7,813.90 | True |
| Microsoft Ads | 2025-10 | 17.06% | $58,409.45 | $58,042.01 | $367.44 | True |
| Microsoft Ads | 2026-03 | 21.90% | $70,322.78 | $70,313.07 | $9.71 | True |
| Microsoft Ads | 2026-06 | -45.21% | $40,583.98 | $47,726.01 | $7,142.03 | True |

Note: Month-over-month channel periods with >=15% spend change are compared against the offline concave spend-response multiplier. Direction accuracy is more important than exact dollar error because unmodeled promos, inventory, and pricing also affect revenue.
