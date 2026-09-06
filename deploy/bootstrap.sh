#!/usr/bin/env bash
# One-shot setup for a fresh Amazon Linux 2023 instance. Safe to re-run.
#
# Installs the chopcast package, configures the required AWC User-Agent,
# and starts the collector under systemd.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/SrivatsaChilla/ChopCast.git}"
BRANCH="${BRANCH:-main}"
REPO="/home/ec2-user/ChopCast"

echo "==> packages"
# The package requires Python >= 3.11 (see pyproject.toml).
sudo dnf install -y git sqlite python3.11 python3.11-pip
PY=$(command -v python3.11)
echo "    $PY ($($PY --version))"

echo "==> repo"
if [ -d "$REPO/.git" ]; then
  git -C "$REPO" fetch --all --quiet && git -C "$REPO" checkout "$BRANCH" && git -C "$REPO" pull --ff-only
else
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO"
fi
cd "$REPO"

echo "==> virtualenv"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -e .
./.venv/bin/python -c "import chopcast; print('    package installed')"

echo "==> configuration"
# AWC filters generic clients, so a real contact is required, not optional.
if [ ! -f .env ]; then
  cp .env.example .env
  if [ -n "${CHOPCAST_CONTACT:-}" ]; then
    sed -i "s|^CHOPCAST_COLLECTOR__USER_AGENT=.*|CHOPCAST_COLLECTOR__USER_AGENT=\"chopcast/0.1 (+${CHOPCAST_CONTACT})\"|" .env
    echo "    User-Agent set to contact ${CHOPCAST_CONTACT}"
  else
    echo "    !! .env created from template."
    echo "    !! Set CHOPCAST_COLLECTOR__USER_AGENT to a real contact before collecting."
    echo "    !! Re-run with: CHOPCAST_CONTACT=you@example.com bash deploy/bootstrap.sh"
  fi
fi
./.venv/bin/chopcast config validate

echo "==> one test pull before enabling the service"
./.venv/bin/chopcast-collector once

echo "==> systemd"
sudo cp deploy/chopcast.service deploy/chopcast-backup.service deploy/chopcast-backup.timer \
        /etc/systemd/system/
chmod +x deploy/backup.sh
sudo systemctl daemon-reload
sudo systemctl enable --now chopcast

echo
echo "==> done. verify with:"
echo "    systemctl status chopcast"
echo "    journalctl -u chopcast -f"
echo "    cd $REPO && ./.venv/bin/chopcast-collector status"
echo
echo "Backups are NOT enabled yet — they need an S3 bucket. See deploy/RUNBOOK.md step 9."
