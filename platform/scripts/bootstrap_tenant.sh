#!/usr/bin/env bash
# Create a tenant + API key against the local gateway.
# Usage: ./scripts/bootstrap_tenant.sh "Acme Clinic"   (run from anywhere; reads platform/.env)
set -euo pipefail
cd "$(dirname "$0")/.."
# Load only ADMIN_TOKEN from .env: no `source`, so values with spaces/metacharacters are safe.
ADMIN_TOKEN="${ADMIN_TOKEN:-$(grep -E '^ADMIN_TOKEN=' .env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//')}"
[ -n "$ADMIN_TOKEN" ] || { echo "ADMIN_TOKEN not found in .env" >&2; exit 1; }
GW="${GATEWAY:-http://localhost:8080}"
NAME="${1:-Test Clinic}"
PY="${PYTHON:-python3}"

TID=$("$PY" - "$GW" "$ADMIN_TOKEN" "$NAME" <<'PYEOF'
import json, sys, urllib.request
gw, tok, name = sys.argv[1:4]
req = urllib.request.Request(f"{gw}/admin/tenants", method="POST",
    data=json.dumps({"name": name, "baa_signed": True}).encode(),
    headers={"x-admin-token": tok, "content-type": "application/json"})
print(json.load(urllib.request.urlopen(req))["tenant_id"])
PYEOF
)
KEY=$("$PY" - "$GW" "$ADMIN_TOKEN" "$TID" <<'PYEOF'
import json, sys, urllib.request
gw, tok, tid = sys.argv[1:4]
req = urllib.request.Request(f"{gw}/admin/tenants/{tid}/keys", method="POST",
    data=json.dumps({"scopes": ["ingest", "query"], "rate_limit_per_min": 120}).encode(),
    headers={"x-admin-token": tok, "content-type": "application/json"})
print(json.load(urllib.request.urlopen(req))["api_key"])
PYEOF
)
echo "tenant_id=$TID"
echo "api_key=$KEY"
echo "# The key is shown once and never stored in plaintext. Export for the eval harness:"
echo "export TENANT_ID=$TID API_KEY=$KEY"
