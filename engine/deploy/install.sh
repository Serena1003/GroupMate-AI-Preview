#!/usr/bin/env bash
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run this installer with sudo.' >&2; exit 1; }
app_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ "$app_dir" = /opt/groupmate/app ] || { echo 'Clone the repository into /opt/groupmate/app first.' >&2; exit 1; }
DEBIAN_FRONTEND=noninteractive apt-get install -y git curl nginx python3 python3-venv poppler-utils ca-certificates
chmod 0755 /opt/groupmate
id groupmate >/dev/null 2>&1 || useradd --system --home-dir /var/lib/groupmate --shell /usr/sbin/nologin groupmate
install -d -m 0700 -o groupmate -g groupmate /var/lib/groupmate
install -d -m 0700 /etc/groupmate
install -d -m 0755 /var/www/groupmate-acme
if [ ! -s /etc/groupmate/groupmate.env ]; then
  python3 - <<'PY'
import os,secrets
p='/etc/groupmate/groupmate.env'
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write('GROUPMATE_OWNER_SECRET='+secrets.token_urlsafe(24)+'\n')
PY
fi
chmod 0600 /etc/groupmate/groupmate.env
install -m 0644 "$app_dir/deploy/groupmate.service" /etc/systemd/system/groupmate.service
# Before HTTPS is configured, only the certificate challenge path is public.
# The app itself stays on loopback; this never exposes a teacher login over HTTP.
install -m 0644 "$app_dir/deploy/nginx-http-bootstrap.conf" /etc/nginx/sites-available/groupmate
ln -sfn /etc/nginx/sites-available/groupmate /etc/nginx/sites-enabled/groupmate
if [ -L /etc/nginx/sites-enabled/default ]; then
  mv /etc/nginx/sites-enabled/default /etc/nginx/default-site.saved
fi
nginx -t
systemctl daemon-reload
systemctl enable --now groupmate
systemctl enable nginx
systemctl reload-or-restart nginx
python3 - <<'PY'
import time,urllib.request
for attempt in range(10):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/',timeout=3) as r:
            assert r.status==200 and b'GroupMate' in r.read()
        print('LOCAL_ENGINE_OK');break
    except Exception:
        if attempt==9:raise
        time.sleep(0.5)
PY
