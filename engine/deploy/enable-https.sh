#!/usr/bin/env bash
set -euo pipefail
[ "$(id -u)" -eq 0 ] || exit 1
public_ip=${1:?Usage: sudo bash deploy/enable-https.sh PUBLIC_IP}
python3 - "$public_ip" <<'PY'
import ipaddress,sys
ipaddress.IPv4Address(sys.argv[1])
PY
[ -s /etc/letsencrypt/live/groupmate-ip/fullchain.pem ] || { echo 'Issue the approved IP certificate first.' >&2; exit 1; }
sed "s/PUBLIC_IP/$public_ip/g" /opt/groupmate/app/deploy/nginx-https.conf.template > /etc/nginx/sites-available/groupmate
nginx -t
systemctl reload nginx
install -m 0644 /opt/groupmate/app/deploy/groupmate-cert-renew.service /etc/systemd/system/groupmate-cert-renew.service
install -m 0644 /opt/groupmate/app/deploy/groupmate-cert-renew.timer /etc/systemd/system/groupmate-cert-renew.timer
systemctl daemon-reload
systemctl enable --now groupmate-cert-renew.timer
