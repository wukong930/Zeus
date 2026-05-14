# Zeus Local Deployment Runbook

This runbook keeps local deployment checks repeatable and separates service health from feature validation.

## Quick Smoke

From the repository root:

```bash
cp .env.example .env
scripts/local_smoke.sh --start
```

Use `--build` when dependencies or Dockerfiles changed:

```bash
scripts/local_smoke.sh --start --build
```

The smoke checks:

- Docker Compose services: `postgres`, `redis`, `backend`, `frontend`
- healthchecks for Postgres, Redis and backend
- `GET /api/health`
- frontend shell at `/`
- World Risk Map route at `/world-map`

## Expected Local URLs

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health`
- Postgres host port: `55432`
- Redis host port: `6379`

## Common Fixes

### Port Already In Use

Check the owner:

```bash
lsof -i :3000 -n -P
lsof -i :8000 -n -P
```

If another app owns the port, either stop it or override ports in `.env`:

```bash
FRONTEND_PORT=3001
BACKEND_PORT=8001
NEXT_PUBLIC_API_URL=http://localhost:8001
CORS_ORIGINS=http://localhost:3001
```

Then run:

```bash
scripts/local_smoke.sh --start
```

### Frontend Shows Old UI

The frontend container bind-mounts `frontend/`, but `.next` can keep stale generated state. Recreate the frontend container:

```bash
docker compose stop frontend
docker compose rm -f frontend
docker compose up -d frontend
```

If it still looks stale:

```bash
docker compose exec frontend rm -rf .next
docker compose restart frontend
```

### Backend Image Is Stale

Rebuild only the backend:

```bash
docker compose up -d --build backend
scripts/local_smoke.sh
```

### Database State Looks Wrong

Do not delete volumes unless you explicitly want to reset local data. First inspect health:

```bash
docker compose ps
docker compose logs --tail=120 postgres backend
```

For a destructive reset:

```bash
docker compose down -v
docker compose up -d --build
```

## Verification Boundary

`scripts/local_smoke.sh` proves the local stack is reachable and core routes render. It does not replace:

- backend unit tests: `cd backend && .venv/bin/python -m pytest -q`
- frontend build: `cd frontend && npm run build`
- browser visual regression for Causal Web / World Risk Map
