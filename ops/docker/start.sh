#!/usr/bin/env bash
# Starts one radreport process inside the container.
#
#   web      the API (uvicorn) on $PORT
#   jobs     the job worker and the outbox relay together; exits when either does, so the host restarts both
#   all      migrate, then the API, the job worker and the outbox relay in one container (a free instance)
#   worker   the job worker alone
#   relay    the outbox relay alone
#   seed     re-run the idempotent seed (demo logins, model catalog)
#   migrate  apply migrations as the database owner, then create or update the app's login role
#   *        any other command, run with the same database settings (e.g. python -m radreport.devtools.seed)
#
# Database settings, in order of preference:
#   RADREPORT_DATABASE_URL           the app's connection (radreport_app_login), used as given, or
#   RADREPORT_OWNER_DATABASE_URL     the owner's connection, from which the app's is derived by
#   + RADREPORT_APP_DB_PASSWORD      swapping in radreport_app_login and this password.
#   RADREPORT_REPLICA_HOST           a read replica's host (a Neon read replica compute); unless
#                                    RADREPORT_DB__REPLICA_URL is set, it is the app's URL on this host.
# A postgres:// or postgresql:// URL is rewritten to name the psycopg driver.
set -euo pipefail

psycopg_url() {
  printf '%s' "$1" | sed -E 's#^postgres(ql)?://#postgresql+psycopg://#'
}

app_url_from_owner() {
  python - <<'EOF'
import os
from urllib.parse import quote, urlsplit, urlunsplit

owner = urlsplit(os.environ["RADREPORT_OWNER_DATABASE_URL"])
host = owner.hostname + (f":{owner.port}" if owner.port else "")
password = quote(os.environ["RADREPORT_APP_DB_PASSWORD"], safe="")
print(urlunsplit((owner.scheme, f"radreport_app_login:{password}@{host}", owner.path, owner.query, "")))
EOF
}

replica_url_from_app() {
  python - <<'EOF'
import os
from urllib.parse import urlsplit, urlunsplit

app = urlsplit(os.environ["RADREPORT_DATABASE_URL"])
credentials = app.netloc.rpartition("@")[0]
print(urlunsplit((app.scheme, f"{credentials}@{os.environ['RADREPORT_REPLICA_HOST']}", app.path, app.query, "")))
EOF
}

if [[ -n "${RADREPORT_OWNER_DATABASE_URL:-}" ]]; then
  export RADREPORT_OWNER_DATABASE_URL="$(psycopg_url "$RADREPORT_OWNER_DATABASE_URL")"
fi
if [[ -n "${RADREPORT_DATABASE_URL:-}" ]]; then
  export RADREPORT_DATABASE_URL="$(psycopg_url "$RADREPORT_DATABASE_URL")"
elif [[ -n "${RADREPORT_OWNER_DATABASE_URL:-}" && -n "${RADREPORT_APP_DB_PASSWORD:-}" ]]; then
  export RADREPORT_DATABASE_URL="$(app_url_from_owner)"
fi
if [[ -n "${RADREPORT_DB__REPLICA_URL:-}" ]]; then
  export RADREPORT_DB__REPLICA_URL="$(psycopg_url "$RADREPORT_DB__REPLICA_URL")"
elif [[ -n "${RADREPORT_REPLICA_HOST:-}" && -n "${RADREPORT_DATABASE_URL:-}" ]]; then
  # Neon replicas share the primary's roles and passwords, so only the host changes; reads keep the app role's RLS.
  export RADREPORT_DB__REPLICA_URL="$(replica_url_from_app)"
fi

migrate() {
  : "${RADREPORT_OWNER_DATABASE_URL:?set RADREPORT_OWNER_DATABASE_URL to the database owner's connection string}"
  : "${RADREPORT_APP_DB_PASSWORD:?set RADREPORT_APP_DB_PASSWORD for the app's login role}"
  # On managed Postgres the owner is not a superuser: a role it creates is usable by it only with SET,
  # and the migrations hand their cross-lab views to the radreport_views role they create.
  PGOPTIONS="${PGOPTIONS:-} -c createrole_self_grant=set,inherit" alembic -x url="$RADREPORT_OWNER_DATABASE_URL" upgrade head
  python -m radreport.db.bootstrap --url "$RADREPORT_OWNER_DATABASE_URL" --app-password "$RADREPORT_APP_DB_PASSWORD"
}

web_command() {
  # Each uvicorn worker writes its metrics here and /metrics merges them; start empty so a restart does not count twice.
  export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/radreport-metrics}"
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
  find "$PROMETHEUS_MULTIPROC_DIR" -maxdepth 1 -type f -name '*.db' -delete
  # Behind the host's TLS proxy: trust X-Forwarded-Proto so the app sees https and sends the Secure admin cookie.
  exec uvicorn radreport.api.app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips '*' "$@"
}

# Runs each command in the background; exits when any one does, so the host restarts them all.
supervise() {
  local pids=() cmd pid stopping=0
  for cmd in "$@"; do
    ( $cmd ) &
    pids+=("$!")
  done
  trap 'stopping=1; kill -TERM "${pids[@]}" 2>/dev/null' TERM INT
  while [[ $stopping -eq 0 ]]; do
    for pid in "${pids[@]}"; do
      kill -0 "$pid" 2>/dev/null || break 2
    done
    sleep 1
  done
  kill -TERM "${pids[@]}" 2>/dev/null || true
  wait || true
  # A deliberate stop is a clean exit; one process ending on its own is a failure, so the host restarts the container.
  [[ $stopping -eq 1 ]] && exit 0
  exit 1
}

command="${1:-web}"
[[ $# -gt 0 ]] && shift

case "$command" in
  web)
    web_command "$@"
    ;;
  worker)
    exec python -m radreport.workers --concurrency "${WORKER_CONCURRENCY:-2}" "$@"
    ;;
  relay)
    exec python -m radreport.events relay "$@"
    ;;
  jobs)
    supervise "python -m radreport.workers --concurrency ${WORKER_CONCURRENCY:-2}" "python -m radreport.events relay"
    ;;
  all)
    # One container for a host with no pre-deploy step or paid workers: migrate on every start (a no-op at head).
    migrate
    supervise "web_command" "python -m radreport.workers --concurrency ${WORKER_CONCURRENCY:-1}" "python -m radreport.events relay"
    ;;
  seed)
    # Safe to repeat: tops up the model catalog and brings the demo logins in step with RADREPORT_DEMO_ACCOUNTS.
    # A database with no labs is also seeded by the API itself on its first start.
    exec python -m radreport.devtools.seed "$@"
    ;;
  migrate)
    migrate
    ;;
  *)
    exec "$command" "$@"
    ;;
esac
