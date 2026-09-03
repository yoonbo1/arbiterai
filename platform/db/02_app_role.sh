#!/bin/bash
# Runs once at first Postgres init (after 01_init.sql). Sets the application role's
# password from the environment; init .sql files cannot read env vars, this can.
set -euo pipefail
: "${PG_APP_PASSWORD:?PG_APP_PASSWORD must be set in the postgres service environment}"
psql -v ON_ERROR_STOP=1 -v pw="$PG_APP_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
ALTER ROLE app_rw PASSWORD :'pw';
SQL
echo "app_rw password set"
