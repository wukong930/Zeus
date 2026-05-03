# Zeus Project Conventions

## Mission

Zeus is a commodity futures research and decision platform. The core chain should remain deterministic, traceable, and backtestable. LLM output may assist with narrative, contradiction analysis, and hypothesis generation, but it must not directly rewrite production trading rules.

Causa source reference for migration work: https://github.com/wukong930/Causa

## Architecture Rules

- Keep business logic in `backend/` Python services. The Next.js app is the operator interface and API proxy.
- Use PostgreSQL + pgvector as the default vector store. Weaviate is an optional later profile only when scale or tenancy requires it.
- Every historical or revised dataset that can affect backtests must preserve point-in-time visibility with `vintage_at`.
- Any future self-learning rule change must go through governance review, shadow validation, and manual approval before production use.

## Local Development

- Backend entrypoint: `backend/app/main.py`
- Health check: `GET /api/health`
- Readiness check: `GET /api/health/ready`
- Frontend dev server: `cd frontend && npm run dev`
- Full stack: `docker compose up --build`

## Coding Standards

- Prefer small, typed Python modules with explicit service boundaries.
- Keep API route modules thin; place domain logic under `backend/app/services/`.
- Use SQLAlchemy async sessions for database access.
- Use Alembic for schema changes.
- Do not introduce production data mutations without an accompanying migration and rollback path.
