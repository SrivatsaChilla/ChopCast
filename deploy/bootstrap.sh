#!/usr/bin/env bash
# One-shot setup for a fresh Amazon Linux 2023 instance. Safe to re-run.
set -euo pipefail

REPO_URL="https://github.com/SrivatsaChilla/ChopCast.git"
HOME_DIR="/home/ec2-user"
REPO="$HOME_DIR/ChopCast"

echo "==> installing packages"
sudo dnf install -y git sqlite python3.11 python3.11-pip 2>/dev/null \
  || sudo dnf install -y git sqlite python3 python3-pip
PY=$(command -v python3.11 || command -v python3)
echo "    using $PY ($($PY --version))"

echo "==> fetching repo"
if [ -d "$REPO/.git" ]; then git -C "$REPO" pull --ff-only; else git clone "$REPO_URL" "$REPO"; fi
cd "$REPO"

echo "==> virtualenv"
[ -d venv ] || "$PY" -m venv venv
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt
./venv/bin/python -c "import pandas, requests; print('    deps OK, pandas', pandas.__version__)"

echo "==> one test pull before enabling the service"
./venv/bin/python collector.py --once

echo "==> installing systemd units"
sudo cp deploy/chopcast.service deploy/chopcast-backup.service deploy/chopcast-backup.timer \
       /etc/systemd/system/
chmod +x deploy/backup.sh
sudo systemctl daemon-reload
sudo systemctl enable --now chopcast

echo
echo "==> done. verify with:"
echo "    systemctl status chopcast"
echo "    journalctl -u chopcast -f"
echo "    cd $REPO && ./venv/bin/python collector.py --health"
echo
echo "Backups are NOT enabled yet -- they need an S3 bucket first."
echo "See deploy/RUNBOOK.md step 8."
