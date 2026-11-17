#!/usr/bin/env bash
# Install hkins systemd units + cron on an Ubuntu server.
#   sudo APP_DIR=/opt/hkins APP_USER=hkins ./install.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/hkins}"
APP_USER="${APP_USER:-hkins}"
VENV="${VENV:-$APP_DIR/venv}"
BACKEND="$APP_DIR/backend"
LOG_DIR="${LOG_DIR:-/var/log/hkins}"
WEB_PORT="${WEB_PORT:-8010}"
QUEUES=(default funds news fund-analysis cards cards-io proposal docai)
HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  echo "Please run as root: sudo $0" >&2
  exit 1
fi
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  echo "User '$APP_USER' does not exist. Create it first, e.g.:" >&2
  echo "  sudo useradd -r -m -d $APP_DIR -s /bin/bash $APP_USER" >&2
  exit 1
fi
if [[ ! -x "$VENV/bin/celery" ]]; then
  echo "Celery not found in $VENV. Activate the venv and install requirements first." >&2
  exit 1
fi

install -d -o "$APP_USER" -g "$APP_USER" "$LOG_DIR"
install -d /etc/hkins

render() { # render <template> <dest>
  sed -e "s|@APP_USER@|$APP_USER|g" \
      -e "s|@APP_DIR@|$APP_DIR|g" \
      -e "s|@VENV@|$VENV|g" \
      -e "s|@BACKEND@|$BACKEND|g" \
      -e "s|@LOG_DIR@|$LOG_DIR|g" \
      -e "s|@WEB_PORT@|$WEB_PORT|g" "$1" > "$2"
}

render "$HERE/systemd/hkins-worker@.service" /etc/systemd/system/hkins-worker@.service
render "$HERE/systemd/hkins-web.service"      /etc/systemd/system/hkins-web.service

# cards-io is IO-bound: 2 concurrent processes (optional override file)
echo "CONCURRENCY=2" > /etc/hkins/worker-cards-io.env

systemctl daemon-reload
for q in "${QUEUES[@]}"; do
  systemctl enable --now "hkins-worker@${q}.service"
done

if "$VENV/bin/python" -c "import gunicorn" >/dev/null 2>&1; then
  systemctl enable --now hkins-web.service
else
  echo "[warn] gunicorn not installed; skipped hkins-web.service" >&2
fi

render "$HERE/cron/hkins.cron" /etc/cron.d/hkins
chmod 644 /etc/cron.d/hkins

echo
echo "Installed. gunicorn binds 127.0.0.1:${WEB_PORT} (override with WEB_PORT=...)."
echo "Cron timezone note:"
echo "  Debian/Ubuntu cron does not support CRON_TZ; set the server timezone instead:"
echo "    sudo timedatectl set-timezone Asia/Hong_Kong"
echo
systemctl --no-pager --no-legend list-units 'hkins-*' || true
echo "Logs: journalctl -u hkins-worker@funds -f   |   $LOG_DIR/cron.log"
