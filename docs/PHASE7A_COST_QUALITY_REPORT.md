# Phase 7a Cost Quality Report

Generated: 2026-05-03

## Scope

This report evaluates the Phase 7a ferrous cost model bootstrap:

- Chain: `JM -> J -> RB` plus `I` and `HC`
- Model outputs: P25/P50/P75/P90 breakeven cost curves
- Signals: `capacity_contraction`, `restart_expectation`, `median_pressure`, `marginal_capacity_squeeze`
- Data mode: public fallback reference pack plus manual low-frequency parameters

## Benchmark Result

The quality API (`/api/cost-models/quality/ferrous`) compared model breakevens with the Phase 7a public reference pack.

| Symbol | Metric | Model | Public Reference | Error |
| --- | --- | ---: | ---: | ---: |
| RB | P75 breakeven | 3356.745 | 3400.0 | 1.27% |
| RB | P90 breakeven | 3612.497 | 3600.0 | 0.35% |
| HC | P75 breakeven | 3661.245 | 3700.0 | 1.05% |
| J | P75 breakeven | 2032.868 | 2050.0 | 0.84% |
| I | P50 breakeven | 827.2 | 830.0 | 0.34% |
| JM | P50 breakeven | 1111.5 | 1120.0 | 0.76% |

Summary:

- Average error: 0.77%
- Max error: 1.27%
- Pass rate under 5% target: 100%

## Historical Signal Cases

| Case | Expected | Triggered | Result |
| --- | --- | --- | --- |
| 2021 production curb cost pressure | `capacity_contraction`, `median_pressure`, `marginal_capacity_squeeze` | all expected signals | Pass |
| 2024 capacity adjustment marginal squeeze | `median_pressure`, `marginal_capacity_squeeze` | all expected signals | Pass |
| Margin recovery restart expectation | `restart_expectation` | expected signal plus marginal squeeze context | Pass |

Signal case hit rate: 100%.

## Purchase Decision

Recommendation: `defer_paid_purchase_monitor_weekly`

The public-source fallback is good enough to continue Phase 7a/7b development without immediately purchasing Zhuochuang, SMM, or Mysteel. Keep a weekly quality review. Revisit paid data when either:

- Average benchmark error rises above 5%
- Historical case hit rate drops below 75%
- Frontend users need intraday precision for live trading decisions

If a paid source becomes necessary, prioritize Mysteel for ferrous operating-rate and steel-margin coverage.

## Limitations

- The reference pack is a public-source bootstrap, not a licensed feed.
- Low-frequency parameters still require manual quarterly review.
- Historical cases validate trigger logic, not full forward PnL.
