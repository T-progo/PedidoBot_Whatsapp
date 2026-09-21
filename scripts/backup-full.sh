#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

BASE="/opt/tunegociolisto"
INFRA="$BASE/infrastructure"
FULL_ROOT="$BASE/backups/full"
LOG_ROOT="$BASE/backups/logs"
TMP_ROOT="$BASE/tmp"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$FULL_ROOT/$TIMESTAMP"
LOG_FILE="$LOG_ROOT/backup-$TIMESTAMP.log"
LOCK_FILE="/run/lock/tunegociolisto-backup.lock"

KUMA_STAGE=""

mkdir -p "$FULL_ROOT" "$LOG_ROOT" "$TMP_ROOT"

exec 9>"$LOCK_FILE"

if ! flock -n 9; then
    echo "ERROR: ya existe otro backup en ejecucion"
    exit 1
fi

exec > >(tee -a "$LOG_FILE") 2>&1

cleanup() {
    RC=$?

    if [ -n "${KUMA_STAGE:-}" ] && [ -d "$KUMA_STAGE" ]; then
        rm -rf -- "$KUMA_STAGE"
    fi

    if [ "$RC" -ne 0 ] && [ -d "${BACKUP_ROOT:-}" ]; then
        rm -f "$BACKUP_ROOT/metadata/VALIDATED" 2>/dev/null || true

        {
            echo "STATUS=FAILED"
            echo "DATE=$(date -Is)"
            echo "EXIT_CODE=$RC"
        } > "$BACKUP_ROOT/FAILED"

        chmod 600 "$BACKUP_ROOT/FAILED" 2>/dev/null || true
        chown tnl:tnl "$BACKUP_ROOT/FAILED" 2>/dev/null || true
    fi

    exit "$RC"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "=================================================="
echo " NEGOCIOLISTO - BACKUP FULL AUTOMATICO"
echo "=================================================="
echo "Inicio  : $(date -Is)"
echo "Destino : $BACKUP_ROOT"
echo

echo "===== PRECHECK ====="

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: ejecutar como root"
    exit 1
fi

for CMD in docker tar sha256sum python3 flock df awk grep; do
    if ! command -v "$CMD" >/dev/null 2>&1; then
        echo "ERROR: comando requerido no disponible: $CMD"
        exit 1
    fi
done

AVAILABLE_KB="$(df -Pk "$BASE" | awk 'NR==2 {print $4}')"
MINIMUM_KB=$((2 * 1024 * 1024))

echo "Espacio libre: $((AVAILABLE_KB / 1024)) MB"

if [ "$AVAILABLE_KB" -lt "$MINIMUM_KB" ]; then
    echo "ERROR: menos de 2 GB libres"
    exit 1
fi

CONTAINERS=(
    tnl-postgresql
    tnl-redis
    tnl-typebot-builder
    tnl-typebot-viewer
    tnl-evolution
    tnl-n8n
    tnl-n8n-runners
    tnl-uptime-kuma
)

for C in "${CONTAINERS[@]}"; do
    STATE="$(docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null || true)"

    if [ "$STATE" != "true" ]; then
        echo "ERROR: contenedor no operativo: $C"
        exit 1
    fi
done

echo "OK: precheck"
echo

mkdir -p \
"$BACKUP_ROOT/postgresql" \
"$BACKUP_ROOT/redis" \
"$BACKUP_ROOT/uptime-kuma" \
"$BACKUP_ROOT/infrastructure/stacks" \
"$BACKUP_ROOT/infrastructure/env" \
"$BACKUP_ROOT/infrastructure/secrets" \
"$BACKUP_ROOT/infrastructure/volumes" \
"$BACKUP_ROOT/infrastructure/nginx" \
"$BACKUP_ROOT/infrastructure/letsencrypt" \
"$BACKUP_ROOT/metadata"

echo "===== POSTGRESQL ====="

DATABASES=(
    evolution
    n8n
    postgres
    tnl_core
    typebot
)

for DB in "${DATABASES[@]}"; do
    echo "Dump: $DB"

    docker exec tnl-postgresql \
        pg_dump \
        -U tnl_admin \
        -Fc \
        "$DB" \
        > "$BACKUP_ROOT/postgresql/$DB.dump"

    if [ ! -s "$BACKUP_ROOT/postgresql/$DB.dump" ]; then
        echo "ERROR: dump vacio: $DB"
        exit 1
    fi
done

docker exec tnl-postgresql \
    pg_dumpall \
    -U tnl_admin \
    --globals-only \
    > "$BACKUP_ROOT/postgresql/globals.sql"

if [ ! -s "$BACKUP_ROOT/postgresql/globals.sql" ]; then
    echo "ERROR: globals.sql vacio"
    exit 1
fi

docker exec tnl-postgresql \
    psql \
    -U tnl_admin \
    -d postgres \
    -Atc "SELECT version();" \
    > "$BACKUP_ROOT/metadata/postgresql-version.txt"

echo "OK: PostgreSQL"
echo

echo "===== REDIS ====="

REDIS_SECRET="$INFRA/secrets/redis_password"

if [ ! -s "$REDIS_SECRET" ]; then
    echo "ERROR: redis_password no encontrado"
    exit 1
fi

REDIS_PASSWORD="$(tr -d '\r\n' < "$REDIS_SECRET")"

REDIS_SAVE="$(
    docker exec \
    -e REDISCLI_AUTH="$REDIS_PASSWORD" \
    tnl-redis \
    redis-cli --raw SAVE
)"

if [ "$REDIS_SAVE" != "OK" ]; then
    echo "ERROR: Redis SAVE fallo"
    unset REDIS_PASSWORD
    exit 1
fi

docker cp \
tnl-redis:/data/dump.rdb \
"$BACKUP_ROOT/redis/dump.rdb" \
>/dev/null

unset REDIS_PASSWORD

if [ ! -s "$BACKUP_ROOT/redis/dump.rdb" ]; then
    echo "ERROR: dump.rdb no generado"
    exit 1
fi

echo "OK: Redis"
echo

echo "===== UPTIME KUMA ====="

KUMA_SRC="$INFRA/volumes/uptime-kuma"
KUMA_DB="$KUMA_SRC/kuma.db"

if [ ! -s "$KUMA_DB" ]; then
    echo "ERROR: kuma.db no encontrado"
    exit 1
fi

KUMA_STAGE="$(mktemp -d "$TMP_ROOT/kuma-backup-XXXXXX")"

mkdir -p "$KUMA_STAGE/data"

cp -a \
"$KUMA_SRC/." \
"$KUMA_STAGE/data/"

rm -f \
"$KUMA_STAGE/data/kuma.db" \
"$KUMA_STAGE/data/kuma.db-wal" \
"$KUMA_STAGE/data/kuma.db-shm"

python3 - "$KUMA_DB" "$KUMA_STAGE/data/kuma.db" <<'PY'
import sqlite3
import sys

source = sys.argv[1]
destination = sys.argv[2]

src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
dst = sqlite3.connect(destination)

src.backup(dst)

result = dst.execute("PRAGMA integrity_check").fetchone()[0]

dst.close()
src.close()

if result != "ok":
    raise SystemExit(f"SQLite integrity_check failed: {result}")

print("SQLite integrity_check: ok")
PY

tar \
--numeric-owner \
-czf "$BACKUP_ROOT/uptime-kuma/uptime-kuma-data.tar.gz" \
-C "$KUMA_STAGE/data" \
.

rm -rf -- "$KUMA_STAGE"
KUMA_STAGE=""

if [ ! -s "$BACKUP_ROOT/uptime-kuma/uptime-kuma-data.tar.gz" ]; then
    echo "ERROR: backup Uptime Kuma vacio"
    exit 1
fi

echo "OK: Uptime Kuma"
echo

echo "===== INFRAESTRUCTURA ====="

tar -czf \
"$BACKUP_ROOT/infrastructure/stacks/stacks.tar.gz" \
-C "$INFRA" \
stacks

tar -czf \
"$BACKUP_ROOT/infrastructure/env/env.tar.gz" \
-C "$INFRA" \
env

tar -czf \
"$BACKUP_ROOT/infrastructure/secrets/secrets.tar.gz" \
-C "$INFRA" \
secrets

tar -czf \
"$BACKUP_ROOT/infrastructure/volumes/auxiliary-volumes.tar.gz" \
-C "$INFRA/volumes" \
evolution storage typebot n8n

tar -czf \
"$BACKUP_ROOT/infrastructure/nginx/nginx-config.tar.gz" \
-C /etc \
nginx

tar -czf \
"$BACKUP_ROOT/infrastructure/letsencrypt/letsencrypt.tar.gz" \
-C /etc \
letsencrypt

for FILE in \
"$BACKUP_ROOT/infrastructure/stacks/stacks.tar.gz" \
"$BACKUP_ROOT/infrastructure/env/env.tar.gz" \
"$BACKUP_ROOT/infrastructure/secrets/secrets.tar.gz" \
"$BACKUP_ROOT/infrastructure/volumes/auxiliary-volumes.tar.gz" \
"$BACKUP_ROOT/infrastructure/nginx/nginx-config.tar.gz" \
"$BACKUP_ROOT/infrastructure/letsencrypt/letsencrypt.tar.gz"
do
    if [ ! -s "$FILE" ]; then
        echo "ERROR: archivo infraestructura vacio: $FILE"
        exit 1
    fi
done

echo "OK: infraestructura"
echo

echo "===== METADATA ====="

docker ps -a \
--format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' \
> "$BACKUP_ROOT/metadata/containers-production.txt"

docker image ls \
> "$BACKUP_ROOT/metadata/docker-images-production.txt"

docker network ls \
> "$BACKUP_ROOT/metadata/docker-networks.txt"

df -h \
> "$BACKUP_ROOT/metadata/filesystem.txt"

{
    echo "NEGOCIOLISTO - BACKUP FULL"
    echo "=========================="
    echo
    echo "Timestamp : $TIMESTAMP"
    echo "Hostname  : $(hostname)"
    echo "Created   : $(date -Is)"
    echo
    echo "PostgreSQL     : OK"
    echo "Redis          : OK"
    echo "Uptime Kuma    : OK"
    echo "Infrastructure : OK"
} > "$BACKUP_ROOT/metadata/MANIFEST.txt"

chown -R tnl:tnl "$BACKUP_ROOT"

find "$BACKUP_ROOT" \
-type d \
-exec chmod 700 {} \;

find "$BACKUP_ROOT" \
-type f \
-exec chmod 600 {} \;

echo "===== SHA256 PREVALIDACION ====="

cd "$BACKUP_ROOT"

find . \
-type f \
! -path './metadata/SHA256SUMS-MASTER' \
! -path './metadata/VALIDATED' \
! -path './FAILED' \
-print0 \
| sort -z \
| xargs -0 sha256sum \
> metadata/SHA256SUMS-MASTER

TOTAL="$(wc -l < metadata/SHA256SUMS-MASTER)"

OK_COUNT="$(
    sha256sum -c metadata/SHA256SUMS-MASTER 2>/dev/null \
    | grep -c ': OK$'
)"

echo "Registrados : $TOTAL"
echo "Validados   : $OK_COUNT"

if [ "$TOTAL" -ne "$OK_COUNT" ]; then
    echo "ERROR: SHA256 prevalidacion fallo"
    exit 1
fi

cat > metadata/VALIDATED <<EOF2
NEGOCIOLISTO BACKUP VALIDATED
STATUS=VALIDATED
TYPE=FULL
CREATED=$(date -Is)
FILES=$TOTAL
EOF2

chown tnl:tnl metadata/VALIDATED
chmod 600 metadata/VALIDATED

rm -f metadata/SHA256SUMS-MASTER

find . \
-type f \
! -path './metadata/SHA256SUMS-MASTER' \
! -path './FAILED' \
-print0 \
| sort -z \
| xargs -0 sha256sum \
> metadata/SHA256SUMS-MASTER

chmod 600 metadata/SHA256SUMS-MASTER
chown tnl:tnl metadata/SHA256SUMS-MASTER

TOTAL_FINAL="$(wc -l < metadata/SHA256SUMS-MASTER)"

OK_FINAL="$(
    sha256sum -c metadata/SHA256SUMS-MASTER 2>/dev/null \
    | grep -c ': OK$'
)"

echo
echo "===== SHA256 FINAL ====="
echo "Archivos registrados : $TOTAL_FINAL"
echo "Archivos validados   : $OK_FINAL"

if [ "$TOTAL_FINAL" -ne "$OK_FINAL" ]; then
    echo "ERROR: SHA256 final fallo"
    exit 1
fi

sha256sum \
"$BACKUP_ROOT/metadata/SHA256SUMS-MASTER" \
> "$FULL_ROOT/$TIMESTAMP.SHA256"

chown tnl:tnl \
"$FULL_ROOT/$TIMESTAMP.SHA256"

chmod 600 \
"$FULL_ROOT/$TIMESTAMP.SHA256"

echo
echo "=================================================="
echo " BACKUP AUTOMATICO COMPLETADO"
echo "=================================================="
echo "Backup    : $BACKUP_ROOT"
echo "Archivos  : $TOTAL_FINAL"
echo "SHA256    : OK"
echo "Estado    : VALIDATED"
echo "Final     : $(date -Is)"
echo "=================================================="
