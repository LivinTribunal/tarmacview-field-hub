#!/usr/bin/env bash
# ============================================================================
# Field Stack Teardown / Reset
#
# Stops the docker compose "field" profile (fieldhub + EMQX + MinIO, plus the
# shared postgres they depend on). Pairs with the monorepo launcher (Phase 1.1)
# as the clean stop/reset half of one-command field setup.
#
# By default this only stops and removes the containers - all data volumes
# survive, so the next start comes back with the device registry, broker state,
# and stored media intact.
#
# With --wipe it also drops the data volumes (emqx-data, minio-data, pgdata),
# a destructive reset back to an empty stack. pgdata is the SHARED postgres
# volume - it holds the fieldhub device registry AND the TarmacView backend
# data, so --wipe throws away more than just field state.
#
# This repo's docker-compose.yml is the field-profile REFERENCE; the full stack
# build contexts (backend, frontend) live in the monorepo. This script targets
# this repo's compose file, so run it from the repo that owns the running stack.
#
# Usage:
#   scripts/field-hub/stop-field.sh           # stop, keep all data
#   scripts/field-hub/stop-field.sh --wipe    # stop AND drop data volumes
#   scripts/field-hub/stop-field.sh --help
#
# Exit 0: stack stopped (and wiped when asked).
# Exit 1: bad usage or docker compose failed.
# ============================================================================
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"

usage() {
  cat <<'EOF'
Stop the docker compose "field" profile (fieldhub + EMQX + MinIO + postgres).

Usage:
  scripts/field-hub/stop-field.sh           stop, keep all data volumes
  scripts/field-hub/stop-field.sh --wipe    stop AND drop data volumes
  scripts/field-hub/stop-field.sh --help    show this help

--wipe drops emqx-data, minio-data, and pgdata. pgdata is the SHARED postgres
volume, so --wipe also discards the TarmacView backend database.
EOF
}

WIPE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --wipe)
      WIPE=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument '${1}'" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker not found on PATH" >&2
  exit 1
fi

down_args=(compose -f "$COMPOSE_FILE" --profile field down)

if [[ "$WIPE" == true ]]; then
  echo "WARNING: --wipe drops the emqx-data, minio-data, and pgdata volumes."
  echo "         pgdata is the SHARED postgres volume - this also discards the"
  echo "         TarmacView backend database, not just field state."
  down_args+=(--volumes)
fi

echo "Stopping field stack (${COMPOSE_FILE})..."
docker "${down_args[@]}"

echo ""
if [[ "$WIPE" == true ]]; then
  echo "Done. Field stack stopped and data volumes dropped."
  echo "Next start rebuilds an empty stack; rerun gen-certs.sh if certs were removed."
else
  echo "Done. Field stack stopped; data volumes kept."
  echo "Restart with: docker compose --profile field up -d"
fi
