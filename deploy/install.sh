#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root." >&2
    exit 1
fi

SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET=/opt/mail-accounts-api
ENV_FILE=/etc/mail-accounts-api/.env

if [ ! -f /app/12-mail/config/postfix-accounts.cf ] || [ -L /app/12-mail/config/postfix-accounts.cf ]; then
    echo "The existing accounts file must be a regular, non-symlink file." >&2
    exit 1
fi
if ! systemctl is-active --quiet mail-accounts-api; then
    if [ -n "$(ss -H -ltn 'sport = :9941')" ]; then
        echo "Port 9941 is already in use; no service has been installed." >&2
        exit 1
    fi
fi

install -d -m 755 "$TARGET"
install -d -m 700 /etc/mail-accounts-api
if systemctl is-active --quiet mail-accounts-api; then
    systemctl stop mail-accounts-api
fi
for file in api.py storage.py run.py manage_accounts.py requirements.txt; do
    install -m 644 "$SOURCE/$file" "$TARGET/$file"
done
# Use the system interpreter: a pyenv interpreter under /root is hidden by ProtectHome.
/usr/bin/python3 -m venv --clear --copies "$TARGET/.venv"
"$TARGET/.venv/bin/python" -m pip install -r "$TARGET/requirements.txt"

if [ ! -e "$ENV_FILE" ]; then
    "$TARGET/.venv/bin/python" - "$ENV_FILE" <<'PY'
import os
import secrets
import sys

fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(
        f"MAIL_API_KEY={secrets.token_urlsafe(48)}\n"
        "MAIL_ACCOUNTS_FILE=/app/12-mail/config/postfix-accounts.cf\n"
        "MAIL_API_HOST=0.0.0.0\n"
        "MAIL_API_PORT=9941\n"
    )
PY
fi
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"
install -m 644 "$SOURCE/deploy/mail-accounts-api.service" /etc/systemd/system/mail-accounts-api.service
systemd-analyze verify /etc/systemd/system/mail-accounts-api.service
systemctl daemon-reload
systemctl enable mail-accounts-api
systemctl restart mail-accounts-api
"$TARGET/.venv/bin/python" - "$ENV_FILE" <<'PY'
import sys
import time
import urllib.error
import urllib.request

from dotenv import dotenv_values

config = dotenv_values(sys.argv[1])
host = config.get("MAIL_API_HOST") or "127.0.0.1"
host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
if ":" in host:
    host = f"[{host}]"
url = f"http://{host}:{config.get('MAIL_API_PORT') or '9941'}/health"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for attempt in range(30):
    try:
        with opener.open(url, timeout=1) as response:
            if response.status == 200:
                break
    except (urllib.error.URLError, TimeoutError):
        time.sleep(1)
else:
    raise SystemExit("API readiness check failed; inspect journalctl -u mail-accounts-api")
PY
systemctl is-active --quiet mail-accounts-api
echo "Service started. Credentials remain in /etc/mail-accounts-api/.env (root, 600)."
