#!/usr/bin/env bash
# MarkovFa — one-line installer for Ubuntu 22.04
#
# Usage (as root or a sudo-capable user):
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/install.sh | sudo bash
#
# What it does:
#   1. Installs system deps (Python 3, Postgres 14, Node.js 20, build tools).
#   2. Clones this repo into /opt/markov-fa (or updates it if it already exists).
#   3. Creates a dedicated postgres role + database.
#   4. Sets up a Python venv and installs bot requirements.
#   5. Installs npm deps and applies the Drizzle schema (`drizzle-kit push`).
#   6. Writes /etc/systemd/system/markov-bot.service and markov-dashboard.service.
#   7. Prompts once for TELEGRAM_BOT_TOKEN (or reads $TELEGRAM_BOT_TOKEN from env).
#   8. Enables and starts both services.
#
# You can safely re-run this script; it's idempotent.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/CHANGE_ME/markov-fa.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/markov-fa}"
DB_NAME="${DB_NAME:-markov_bot}"
DB_USER="${DB_USER:-markov}"
DB_PASS="${DB_PASS:-$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 24)}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"
SERVICE_USER="${SERVICE_USER:-markov}"

log() { echo -e "\n\033[1;32m==>\033[0m $*"; }
warn() { echo -e "\n\033[1;33m[warn]\033[0m $*"; }
die() { echo -e "\n\033[1;31m[fatal]\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Please run as root (use sudo)."

log "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git build-essential \
  python3 python3-venv python3-pip python3-dev \
  postgresql postgresql-contrib \
  gnupg

if ! command -v node >/dev/null 2>&1 || [[ "$(node -v 2>/dev/null | cut -c2- | cut -d. -f1)" -lt 20 ]]; then
  log "Installing Node.js 20 (NodeSource)"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

log "Ensuring service user '${SERVICE_USER}' exists"
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

log "Cloning / updating repo into ${INSTALL_DIR}"
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "${INSTALL_DIR}" pull --ff-only
else
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
fi
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

log "Ensuring Postgres role and database"
systemctl enable --now postgresql
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" \
  | grep -q 1 || sudo -u postgres psql -c \
  "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" \
  | grep -q 1 || sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"

DB_URL="postgresql://${DB_USER}:${DB_PASS}@127.0.0.1:5432/${DB_NAME}"

log "Writing .env files"
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  if [[ -f "${INSTALL_DIR}/bot/.env" ]] && grep -q '^TELEGRAM_BOT_TOKEN=' "${INSTALL_DIR}/bot/.env"; then
    TELEGRAM_BOT_TOKEN="$(grep '^TELEGRAM_BOT_TOKEN=' "${INSTALL_DIR}/bot/.env" | head -n1 | cut -d= -f2-)"
  else
    read -rp "Enter your Telegram bot token (from @BotFather): " TELEGRAM_BOT_TOKEN
  fi
fi
[[ -n "${TELEGRAM_BOT_TOKEN}" ]] || die "TELEGRAM_BOT_TOKEN is required"

cat >"${INSTALL_DIR}/bot/.env" <<EOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
DATABASE_URL=${DB_URL}
DEFAULT_RANDOM_MIN=40
DEFAULT_RANDOM_MAX=120
LOG_LEVEL=INFO
EOF

cat >"${INSTALL_DIR}/.env" <<EOF
DATABASE_URL=${DB_URL}
EOF

chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/bot/.env" "${INSTALL_DIR}/.env"
chmod 600 "${INSTALL_DIR}/bot/.env" "${INSTALL_DIR}/.env"

log "Setting up Python venv and installing bot deps"
sudo -u "${SERVICE_USER}" bash -lc "
  cd '${INSTALL_DIR}' &&
  python3 -m venv .venv &&
  .venv/bin/pip install --upgrade pip wheel &&
  .venv/bin/pip install -r bot/requirements.txt
"

log "Installing npm deps and building dashboard"
sudo -u "${SERVICE_USER}" bash -lc "
  cd '${INSTALL_DIR}' &&
  npm ci --no-audit --no-fund &&
  npx drizzle-kit push &&
  npm run build
"

log "Writing systemd units"
cat >/etc/systemd/system/markov-bot.service <<EOF
[Unit]
Description=MarkovFa Persian Telegram Bot
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/bot/.env
ExecStart=${INSTALL_DIR}/.venv/bin/python -m bot.main
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/markov-dashboard.service <<EOF
[Unit]
Description=MarkovFa Next.js Dashboard
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
Environment=NODE_ENV=production
Environment=PORT=${DASHBOARD_PORT}
ExecStart=/usr/bin/npm run start -- -p ${DASHBOARD_PORT}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now markov-bot.service
systemctl enable --now markov-dashboard.service

log "✅ Done."
echo
echo "  • Bot service:       systemctl status markov-bot"
echo "  • Dashboard service: systemctl status markov-dashboard"
echo "  • Dashboard URL:     http://<server-ip>:${DASHBOARD_PORT}"
echo "  • Bot logs:          journalctl -u markov-bot -f"
echo
echo "Postgres credentials (saved in ${INSTALL_DIR}/bot/.env):"
echo "  DATABASE_URL=${DB_URL}"
