6#!/usr/bin/env bash
# LexMetra PostgreSQL 18 Service Launcher (Port 5433)

PGDATA="/home/PRC/Downloads/SIH LATEST/backend/db/data_local"
PGCTL="/usr/pgsql-18/bin/pg_ctl"

if ss -tlpn | grep -q ":5433 "; then
    echo "[OK] PostgreSQL is already running on port 5433."
    exit 0
fi

echo "[*] Starting PostgreSQL on port 5433..."
if [ -f "$PGDATA/postmaster.pid" ]; then
    rm -f "$PGDATA/postmaster.pid"
fi

"$PGCTL" -D "$PGDATA" -l "$PGDATA/server.log" start
sleep 2

if ss -tlpn | grep -q ":5433 "; then
    echo "[OK] PostgreSQL cluster is active and listening on port 5433."
else
    echo "[ERROR] PostgreSQL failed to bind to port 5433. Check $PGDATA/server.log"
    exit 1
fi
