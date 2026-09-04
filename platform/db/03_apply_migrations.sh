#!/bin/bash
# First-init hook: apply db/migrations/*.sql in order so a fresh volume matches a migrated one.
# Existing volumes: `make migrate` runs the same files through psql. Both are idempotent.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
SQL
for f in /docker-entrypoint-initdb.d/migrations/*.sql; do
  [ -e "$f" ] || continue
  n=$(basename "$f")
  if psql -tA --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "SELECT 1 FROM schema_migrations WHERE name='$n'" | grep -q 1; then
    echo "migration $n already applied"; continue
  fi
  echo "applying migration $n"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "INSERT INTO schema_migrations(name) VALUES ('$n')"
done
