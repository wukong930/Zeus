#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

START_STACK=0
BUILD_STACK=0
REGRESSION_CHECKS=0
TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-90}"

usage() {
  cat <<'USAGE'
Usage: scripts/local_smoke.sh [--start] [--build] [--timeout SECONDS]

Checks the local Zeus Docker stack without mutating persisted data.

Options:
  --start            Run docker compose up -d before checking health.
  --build            Use with --start to rebuild images.
  --regression       Also check key API contracts and high-risk frontend routes.
  --timeout SECONDS  Wait time for service health, default 90.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start)
      START_STACK=1
      shift
      ;;
    --build)
      BUILD_STACK=1
      shift
      ;;
    --regression)
      REGRESSION_CHECKS=1
      shift
      ;;
    --timeout)
      TIMEOUT_SECONDS="${2:?Missing timeout value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 2
  fi
}

require_command docker
require_command curl
require_command python3

if [[ "$START_STACK" -eq 1 ]]; then
  compose_args=(up -d)
  if [[ "$BUILD_STACK" -eq 1 ]]; then
    compose_args+=(--build)
  fi
  compose_args+=(postgres redis backend frontend)
  echo "Starting Zeus stack: docker compose ${compose_args[*]}"
  docker compose "${compose_args[@]}"
fi

check_compose_health() {
  docker compose ps --format json | python3 -c '
import json
import sys

required = ["postgres", "redis", "backend", "frontend"]
health_required = {"postgres", "redis", "backend"}
seen = {}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    item = json.loads(line)
    service = item.get("Service") or item.get("Name")
    if service:
        seen[service] = item

problems = []
for service in required:
    item = seen.get(service)
    if not item:
        problems.append(f"{service}: missing")
        continue
    state = str(item.get("State", "")).lower()
    health = str(item.get("Health", "")).lower()
    status = item.get("Status", "")
    if state != "running":
        problems.append(f"{service}: state={state or status}")
        continue
    if service in health_required and health != "healthy":
        problems.append(f"{service}: health={health or status}")

if problems:
    print("; ".join(problems))
    sys.exit(1)

print("compose services healthy: " + ", ".join(required))
'
}

deadline=$((SECONDS + TIMEOUT_SECONDS))
until check_compose_health; do
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for Docker Compose health after ${TIMEOUT_SECONDS}s" >&2
    docker compose ps
    exit 1
  fi
  sleep 3
done

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_URL="http://localhost:${BACKEND_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

check_http() {
  local label="$1"
  local url="$2"
  local needle="${3:-}"
  local tmp
  tmp="$(mktemp)"
  if ! curl -fsS --max-time 20 "$url" -o "$tmp"; then
    rm -f "$tmp"
    echo "${label}: request failed (${url})" >&2
    return 1
  fi
  if [[ -n "$needle" ]] && ! grep -q "$needle" "$tmp"; then
    rm -f "$tmp"
    echo "${label}: response did not contain '${needle}' (${url})" >&2
    return 1
  fi
  rm -f "$tmp"
  echo "${label}: ok (${url})"
}

check_json_keys() {
  local label="$1"
  local url="$2"
  shift 2
  local tmp
  tmp="$(mktemp)"
  if ! curl -fsS --max-time 20 "$url" -o "$tmp"; then
    rm -f "$tmp"
    echo "${label}: request failed (${url})" >&2
    return 1
  fi
  python3 - "$tmp" "$label" "$@" <<'PY'
import json
import sys

path, label, *keys = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

missing = []
for key in keys:
    cursor = payload
    for part in key.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
            continue
        missing.append(key)
        break

if missing:
    print(f"{label}: missing keys: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)
print(f"{label}: ok")
PY
  rm -f "$tmp"
  echo "${label}: contract ok (${url})"
}

check_json_array() {
  local label="$1"
  local url="$2"
  local tmp
  tmp="$(mktemp)"
  if ! curl -fsS --max-time 20 "$url" -o "$tmp"; then
    rm -f "$tmp"
    echo "${label}: request failed (${url})" >&2
    return 1
  fi
  python3 - "$tmp" "$label" <<'PY'
import json
import sys

path, label = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

if not isinstance(payload, list):
    print(f"{label}: expected JSON array, got {type(payload).__name__}", file=sys.stderr)
    sys.exit(1)
print(f"{label}: ok ({len(payload)} rows)")
PY
  rm -f "$tmp"
  echo "${label}: contract ok (${url})"
}

check_http "backend health" "${BACKEND_URL}/api/health" '"status":"ok"'
check_http "frontend shell" "${FRONTEND_URL}" "Zeus"
check_http "market quote strip" "${FRONTEND_URL}" "商品报价"
check_http "world map route" "${FRONTEND_URL}/world-map" "世界风险地图"

if [[ "$REGRESSION_CHECKS" -eq 1 ]]; then
  check_json_keys \
    "runtime heartbeat" \
    "${BACKEND_URL}/api/runtime/heartbeat" \
    generated_at \
    active_signals \
    drift.status \
    drift.notification.title \
    calibration.samples \
    scheduler.handler_coverage \
    status
  check_json_keys \
    "causal web graph" \
    "${BACKEND_URL}/api/causal-web?limit=8" \
    generated_at \
    nodes \
    edges \
    source_counts
  check_json_keys \
    "world map snapshot" \
    "${BACKEND_URL}/api/world-map" \
    generatedAt \
    regions \
    summary.regions \
    layers
  check_json_keys \
    "settings snapshot" \
    "${BACKEND_URL}/api/settings/snapshot" \
    generated_at \
    data_sources \
    scheduler.health.handler_coverage \
    llm_usage.calls \
    llm_providers \
    alert_dedup.daily_alert_limit \
    notifications.source \
    adversarial_runtime.mode
  check_json_array \
    "alerts list" \
    "${BACKEND_URL}/api/alerts?limit=5"
  check_json_array \
    "market data recent" \
    "${BACKEND_URL}/api/market-data/recent?symbols=RB,HC&limit=2"
  check_json_array \
    "trade plans list" \
    "${BACKEND_URL}/api/recommendations?limit=5"

  check_http "causal web route" "${FRONTEND_URL}/causal-web"
  check_http "event intelligence route" "${FRONTEND_URL}/event-intelligence"
  check_http "trade plans route" "${FRONTEND_URL}/trade-plans"
fi

echo "Zeus local smoke passed."
