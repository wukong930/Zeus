# Frontend Data Load Audit

Date: 2026-05-14

This audit records which implemented frontend pages are backed by runtime APIs and which pieces still use static configuration, empty states, or explicit degraded fallbacks.

## Verification

Local stack status:

```bash
scripts/local_smoke.sh
```

Primary page shells returned HTTP 200 locally:

- `/`
- `/alerts`
- `/trade-plans`
- `/portfolio`
- `/causal-web`
- `/news`
- `/event-intelligence`
- `/industry`
- `/sectors`
- `/future-lab`
- `/forge`
- `/notebook`
- `/analytics`
- `/governance`
- `/settings`
- `/world-map`

Core API entrypoints verified against the local backend include:

- `/api/alerts`
- `/api/recommendations`
- `/api/positions`
- `/api/risk/var`
- `/api/risk/stress`
- `/api/causal-web`
- `/api/world-map`
- `/api/world-map/tiles`
- `/api/news-events`
- `/api/event-intelligence`
- `/api/event-intelligence/impact-links`
- `/api/event-intelligence/quality`
- `/api/governance/reviews`
- `/api/attribution/report`
- `/api/cost-models/{symbol}/chain`
- `/api/cost-models/quality/{sector}`
- `/api/notebook`
- `/api/scheduler`
- `/api/data-sources`
- `/api/shadow/calibration`
- `/api/drift/metrics`
- `/api/strategies/backtest-quality`

If a running backend container returns 404 for newly added endpoints that exist in `backend/app/main.py`, rebuild the backend image:

```bash
docker compose up -d --build backend
```

## Page Matrix

| Page | Runtime source | Fallback behavior | Notes |
| --- | --- | --- | --- |
| `/` Command Center | alerts, positions, causal web, sector snapshot, LLM usage, calibration | empty/degraded state per card | No fixed demo results are rendered when APIs fail. |
| `/alerts` | `/api/alerts` | empty unavailable state | Real alert rows only. |
| `/trade-plans` | `/api/recommendations` plus latest market rows | empty unavailable state | Real recommendations only. |
| `/portfolio` | positions, VaR, stress, correlation, market rows | partial degradation by section | Positions are required; risk sections can degrade independently. |
| `/causal-web` | `/api/causal-web` | empty unavailable state | Scope filters use URL params; no sample graph fallback. |
| `/news` | news events plus event-intelligence links | empty unavailable state | Event-intelligence sidebar degrades independently. |
| `/event-intelligence` | event-intelligence items, links, quality, audit logs | empty unavailable state | Governance edits are API-backed. |
| `/industry` | cost chain, cost history, quality report | empty/degraded state | Cost model public fallback is backend-labeled data, not frontend mock. |
| `/sectors` | alerts plus market-data-derived sector snapshot | empty/degraded state | Phase 10.27 removed deterministic fake factor bars; runtime factors now derive from market coverage, signal activity, direction strength, and internal alignment. |
| `/future-lab` | scenario simulation API after user runs a scenario | explicit degraded result if backend uses static base price | Presets are input templates; output is not shown until backend returns a report. |
| `/forge` | backtest quality summary | degraded insufficient-sample state | No hard-coded backtest performance. |
| `/notebook` | notebook API | empty unavailable state | No fixed demo notes. |
| `/analytics` | attribution, calibration, drift, learning hypotheses | section-level unavailable states | Uses real reports; charts render empty if samples are missing. |
| `/governance` | governance review queue | empty unavailable state | Requires backend image with governance router included. |
| `/settings` | data sources, scheduler, LLM, alert dedup, notifications | section-level unavailable states | Toggles persist through settings API. |
| `/world-map` | world map snapshot plus tiles | unavailable banner / empty states | Backend can return baseline/partial data quality per region. |

## Remaining Static Inputs

These are intentional configuration or input templates, not runtime result mocks:

- `frontend/src/data/sectorUniverse.ts`: commodity taxonomy and display grouping used to request market and alert data.
- `frontend/src/app/future-lab/page.tsx`: scenario presets and slider defaults used as user-editable inputs.
- `frontend/src/app/world-map/page.tsx`: visual layer defaults and render-budget constants.

## Follow-Up

- Continue browser visual regression for Causal Web and World Risk Map after layout-heavy changes.
- Keep backend data quality labels visible when backend services use public fallback or baseline data.
- Add focused page-level smoke checks if a route gains high-risk interactions such as write operations or WebGL-heavy rendering.
