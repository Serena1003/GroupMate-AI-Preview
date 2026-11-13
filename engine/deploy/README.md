# Single-server deployment

The browser UI and Python engine run together. Nginx terminates HTTPS; the
engine only listens on 127.0.0.1:8765. XIPU model calls stay server-side.

- Source checkout: `/opt/groupmate/app` (private GitHub repository).
- Runtime secrets: `/etc/groupmate/groupmate.env`, root-owned, mode 0600.
- Persistent classroom state: `/var/lib/groupmate/data/classroom.sqlite`.
- No local classroom database or historical uploads are included in Git.
- Run the app with systemd as the unprivileged `groupmate` account.
- Use a repository-scoped, read-only server deploy key for Git pulls.

## Install

Clone into `/opt/groupmate/app`, then run `sudo bash deploy/install.sh`.
The initial HTTP endpoint serves only ACME challenges and a preparation page.
Set `GROUPMATE_XIPU_WORKFLOW_KEY` in the protected runtime environment file.
The teacher password is `GROUPMATE_OWNER_SECRET` in that file; never commit it.

For domainless HTTPS, install Certbot 5.4+ in `/opt/groupmate/certbot` and request
an IP certificate with the `shortlived` profile and webroot
`/var/www/groupmate-acme`. Certificate issuance requires the owner's agreement
to the certificate authority's terms. After issuance, run:

```sh
sudo bash deploy/enable-https.sh YOUR_PUBLIC_IP
```

The renewal timer checks twice daily and reloads Nginx after renewal. Keep
port 80 available for HTTP-01 validation and port 443 for the classroom.

## Update

Push reviewed source to `main`, then run on the server:

```sh
sudo bash /opt/groupmate/app/deploy/update.sh
```

The update makes an SQLite backup first, requires a clean checkout, pulls
without rewriting history, restarts the service and checks the local engine.

## Operations

```sh
sudo systemctl status groupmate nginx --no-pager
sudo journalctl -u groupmate -n 50 --no-pager
sudo systemctl list-timers groupmate-cert-renew.timer
```

A clean cloud instance starts without classroom records. Use a synthetic class
for the initial external end-to-end check, then create the real teaching
activity through the teacher UI. Knowledge-base integration remains paused.
