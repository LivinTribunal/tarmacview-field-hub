#!/usr/bin/env bash
# ============================================================================
# Field Hub TLS Material Generator
#
# Creates a local CA plus per-service server certificates for the docker
# compose "field" profile (fieldhub HTTPS, EMQX MQTTS, MinIO TLS-ready).
# Everything lands in a git-ignored certs/ directory at the repo root:
#
#   certs/ca/        ca.crt, ca.key                    (CA key never mounted)
#   certs/fieldhub/  server.crt, server.key, ca.crt
#   certs/emqx/      server.crt, server.key, ca.crt
#   certs/minio/     public.crt, private.key, ca.crt   (MinIO's expected names)
#
# The CA is generated once and reused on later runs - it gets installed on
# the RCs during provisioning, so regenerating it would invalidate them.
# Service certs are regenerated on every run, e.g. after the laptop's LAN IP
# on the travel router changes.
#
# Each service cert carries SANs for its compose-internal DNS name,
# localhost/127.0.0.1, the hub DNS name, and (when given) the laptop's LAN
# IP - DJI Pilot 2 on the RC connects via that IP, so pass it for field use.
#
# Usage:
#   scripts/field-hub/gen-certs.sh [HUB_IP]
#
# Env overrides:
#   HUB_IP      LAN IP of the laptop on the travel router (default: none)
#   HUB_DNS     extra DNS SAN (default: hub.tarmacview.local)
#   CERTS_DIR   output directory (default: <repo>/certs)
#   DAYS        certificate validity in days (default: 825)
#
# Exit 0: all certs written.
# Exit 1: openssl missing or generation failed.
# ============================================================================
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

HUB_IP="${1:-${HUB_IP:-}}"
HUB_DNS="${HUB_DNS:-hub.tarmacview.local}"
CERTS_DIR="${CERTS_DIR:-${REPO_ROOT}/certs}"
DAYS="${DAYS:-825}"
CA_DIR="${CERTS_DIR}/ca"

if ! command -v openssl >/dev/null 2>&1; then
  echo "Error: openssl not found on PATH" >&2
  exit 1
fi

if [[ -n "$HUB_IP" ]] && ! [[ "$HUB_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: HUB_IP must be an IPv4 address (got '${HUB_IP}')" >&2
  exit 1
fi

mkdir -p "$CA_DIR" "$CERTS_DIR/fieldhub" "$CERTS_DIR/emqx" "$CERTS_DIR/minio"

# ----------------------------------------------------------------------------
# Local CA - created once, reused afterwards
# ----------------------------------------------------------------------------
if [[ -f "$CA_DIR/ca.key" && -f "$CA_DIR/ca.crt" ]]; then
  echo "Reusing existing CA at ${CA_DIR} (regenerating would invalidate provisioned RCs)"
else
  echo "Generating local CA..."
  openssl genrsa -out "$CA_DIR/ca.key" 4096 2>/dev/null
  openssl req -x509 -new -nodes -key "$CA_DIR/ca.key" -sha256 -days "$DAYS" \
    -subj "/O=TarmacView/CN=TarmacView Field CA" -out "$CA_DIR/ca.crt"
  chmod 600 "$CA_DIR/ca.key"
fi

# ----------------------------------------------------------------------------
# Per-service certs - regenerated on every run
# ----------------------------------------------------------------------------
gen_service_cert() {
  local service="$1" crt_name="$2" key_name="$3"
  local dir="${CERTS_DIR}/${service}"
  local san="DNS:${service},DNS:localhost,DNS:${HUB_DNS},IP:127.0.0.1"

  if [[ -n "$HUB_IP" ]]; then
    san="${san},IP:${HUB_IP}"
  fi

  echo "Generating ${service} cert (SANs: ${san})..."
  openssl genrsa -out "$dir/$key_name" 2048 2>/dev/null
  openssl req -new -key "$dir/$key_name" \
    -subj "/O=TarmacView/CN=${service}" -out "$dir/${service}.csr"
  openssl x509 -req -in "$dir/${service}.csr" \
    -CA "$CA_DIR/ca.crt" -CAkey "$CA_DIR/ca.key" -CAcreateserial \
    -days "$DAYS" -sha256 -out "$dir/$crt_name" \
    -extfile <(printf 'subjectAltName=%s\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n' "$san") \
    2>/dev/null
  rm -f "$dir/${service}.csr"
  cp "$CA_DIR/ca.crt" "$dir/ca.crt"

  # containers run as non-root users and bind mounts keep host ownership,
  # so keys need world-read. local dev CA material only, certs/ is git-ignored.
  chmod 644 "$dir/$key_name" "$dir/$crt_name" "$dir/ca.crt"
}

gen_service_cert fieldhub server.crt server.key
gen_service_cert emqx server.crt server.key
gen_service_cert minio public.crt private.key

echo ""
echo "Done. TLS material written to ${CERTS_DIR}/"
if [[ -z "$HUB_IP" ]]; then
  echo "Note: no HUB_IP given - certs carry no LAN IP SAN. RCs on the travel"
  echo "router will fail TLS verification; rerun with the laptop's static IP:"
  echo "  scripts/field-hub/gen-certs.sh 192.168.8.100"
fi
echo "Next steps:"
echo "  1. docker compose --profile field up -d --build"
echo "  2. install ${CERTS_DIR}/ca/ca.crt on each RC during provisioning"
