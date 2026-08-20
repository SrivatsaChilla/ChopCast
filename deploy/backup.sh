#!/usr/bin/env bash
# Nightly SQLite -> S3 backup.
#
# Uses `sqlite3 .backup` rather than `cp`: the collector writes every 10 minutes,
# and copying a live SQLite file can capture a torn page mid-write. `.backup`
# takes a consistent snapshot of a database that is actively being written.
set -euo pipefail

REPO="${REPO:-/home/ec2-user/ChopCast}"
DB="$REPO/pireps.db"
BUCKET="${CHOPCAST_BUCKET:?set CHOPCAST_BUCKET, e.g. export CHOPCAST_BUCKET=chopcast-backups-yourname}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "$DB" ] || { echo "no database at $DB"; exit 1; }

echo "snapshotting $DB"
sqlite3 "$DB" ".backup '$TMP/pireps.db'"

# Sanity-check the snapshot before shipping it. A corrupt backup that uploads
# cleanly is worse than a failed backup, because it looks like success.
ROWS="$(sqlite3 "$TMP/pireps.db" 'SELECT COUNT(*) FROM reports;')"
[ "$ROWS" -gt 0 ] || { echo "snapshot has 0 rows, refusing to upload"; exit 1; }
echo "snapshot OK: $ROWS rows"

gzip -9 "$TMP/pireps.db"
aws s3 cp "$TMP/pireps.db.gz" "s3://$BUCKET/pireps-$STAMP.db.gz"
aws s3 cp "$TMP/pireps.db.gz" "s3://$BUCKET/pireps-latest.db.gz"
echo "uploaded $ROWS rows to s3://$BUCKET/ (stamped + latest)"
