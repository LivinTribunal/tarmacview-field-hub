#!/usr/bin/env bash
# register a wayline (KMZ) into the fieldhub library so DJI Pilot 2 can sync it -
# stands in for the monorepo backend's dispatch call during emulator testing.
#
# usage: seed-wayline.sh <file.kmz> <name> <drone_model_key> [payload_model_keys]
#   e.g. seed-wayline.sh exports/rwy22.kmz "RWY22 PAPI" 0-89-0 1-53-0
#
# drone/payload keys are domain-type-subtype (docs/specs/dji-cloud-api-reference.md §6).
# HUB_URL defaults to the nginx proxy; FIELDHUB_SHARED_SECRET must match the stack.
set -euo pipefail

KMZ="${1:?usage: seed-wayline.sh <file.kmz> <name> <drone_model_key> [payload_model_keys]}"
NAME="${2:?name required}"
DRONE_KEY="${3:?drone_model_key required - see dji-cloud-api-reference.md §6}"
PAYLOAD_KEYS="${4:-}"

HUB_URL="${HUB_URL:-http://localhost:8080}"
SECRET="${FIELDHUB_SHARED_SECRET:-emulator-secret}"

[ -f "$KMZ" ] || { echo "no such file: $KMZ" >&2; exit 1; }

WAYLINE_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
MISSION_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
SIGN="$(python3 -c 'import hashlib,sys; print(hashlib.md5(open(sys.argv[1],"rb").read()).hexdigest())' "$KMZ")"
OBJECT_KEY="wayline/${WAYLINE_ID}.kmz"

echo "registering '$NAME' (drone=$DRONE_KEY payload=${PAYLOAD_KEYS:-none}) -> $HUB_URL"
curl -fsS -X POST "$HUB_URL/internal/api/v1/waylines" \
  -H "X-Hub-Secret: $SECRET" \
  -F "wayline_id=$WAYLINE_ID" \
  -F "mission_id=$MISSION_ID" \
  -F "name=$NAME" \
  -F "object_key=$OBJECT_KEY" \
  -F "drone_model_key=$DRONE_KEY" \
  -F "payload_model_keys=$PAYLOAD_KEYS" \
  -F "sign=$SIGN" \
  -F "file=@${KMZ};type=application/vnd.google-earth.kmz"
echo
echo "done: wayline_id=$WAYLINE_ID"
