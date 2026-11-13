#!/usr/bin/env bash
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
cd /opt/groupmate/app
[ -z "$(git status --porcelain)" ] || { echo 'Server checkout contains local edits; review them before updating.' >&2; exit 1; }
install -d -m 0700 /var/backups/groupmate
python3 - <<'PY'
import sqlite3,datetime
from pathlib import Path
source=Path('/var/lib/groupmate/data/classroom.sqlite')
if source.exists():
    with sqlite3.connect(source) as src,sqlite3.connect('/var/backups/groupmate/classroom-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sqlite') as dest:src.backup(dest)
PY
git pull --ff-only origin main
systemctl restart groupmate
python3 - <<'PY'
import time,urllib.request
for attempt in range(10):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/',timeout=2) as response:
            if response.status!=200:raise RuntimeError('Engine not ready')
        print('LOCAL_ENGINE_OK');break
    except Exception:
        if attempt==9:raise
        time.sleep(0.5)
PY
git log -1 --format='Deployed %h %s'
