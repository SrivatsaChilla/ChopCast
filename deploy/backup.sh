#!/usr/bin/env bash
# Nightly SQLite -> S3 backup.
#
# Uses `sqlite3 .backup` rather than `cp`: the collector writes every 10
# minutes, and copying a live SQLite file can capture a torn page. `.backup`
# takes a consistent snapshot of a database that is being written.
set -euo pipefail

REPO="${REPO:-/home/ec2-user/ChopCast}"
BUCKET="${CHOPCAST_BUCKET:?set CHOPCAST_BUCKET, e.g. export CHOPCAST_BUCKET=chopcast-backups-yourname}"

# Ask the package where the database is rather than hardcoding it: the path
# comes from configs/ + .env and is not necessarily under the repo.
DB="$("$REPO/.venv/bin/python" -c \
  'from chopcast.config import Settings; print(Settings.load().to_paths().raw_db_path)')"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "$DB" ] || { echo "no database at $DB"; exit 1; }
echo "snapshotting $DB"
sqlite3 "$DB" ".backup '$TMP/pireps.db'"

# Sanity-check before shipping. A corrupt backup that uploads cleanly is
# worse than a failed one, because it looks like success.
ROWS="$(sqlite3 "$TMP/pireps.db" 'SELECT COUNT(*) FROM reports;')"
[ "$ROWS" -gt 0 ] || { echo "snapshot has 0 rows, refusing to upload"; exit 1; }
echo "snapshot OK: $ROWS rows"

gzip -9 "$TMP/pireps.db"
aws s3 cp "$TMP/pireps.db.gz" "s3://$BUCKET/pireps-$STAMP.db.gz"
aws s3 cp "$TMP/pireps.db.gz" "s3://$BUCKET/pireps-latest.db.gz"
echo "uploaded $ROWS rows to s3://$BUCKET/ (stamped + latest)"
