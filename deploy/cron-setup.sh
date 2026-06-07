#!/bin/bash
# Setup cron job for kinopois on Linux VPS.
# Run once after cloning: bash deploy/cron-setup.sh

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO_DIR/data/logs"
LOG_FILE="$LOG_DIR/cron.log"
CRON_HOUR="${CRON_HOUR:-21}"      # default: 21:00 every day (Moscow)
CRON_MINUTE="${CRON_MINUTE:-0}"
CRON_TZ="${CRON_TZ:-Europe/Moscow}"
LIMIT="${LIMIT:-200}"

mkdir -p "$LOG_DIR"

if docker compose version >/dev/null 2>&1; then
  RUN_CMD="cd $REPO_DIR && docker compose run --rm kinopois-prepare run-base-pipeline --limit $LIMIT"
elif docker image inspect kinopois:prod >/dev/null 2>&1; then
  RUN_CMD="docker run --rm --env-file $REPO_DIR/.env -v $REPO_DIR/data:/app/data -v $REPO_DIR/credentials:/app/credentials:ro kinopois:prod run-base-pipeline --limit $LIMIT"
else
  echo "ERROR: neither 'docker compose' nor image 'kinopois:prod' is available."
  echo "Build image first: docker build -t kinopois:prod $REPO_DIR"
  exit 1
fi

CRON_LINE="$CRON_MINUTE $CRON_HOUR * * * $RUN_CMD >> $LOG_FILE 2>&1"

# Add to crontab if not already there
(
  (crontab -l 2>/dev/null || true) \
    | awk '!/kinopois-prepare run-base-pipeline/ && !/kinopois:prod run-base-pipeline/ && $0 != "CRON_TZ='"$CRON_TZ"'"'
  echo "CRON_TZ=$CRON_TZ"
  echo "$CRON_LINE"
) | crontab -

echo "Cron job set: runs at ${CRON_HOUR}:$(printf '%02d' "$CRON_MINUTE") every day ($CRON_TZ)"
echo "Logs: $LOG_FILE"
echo ""
echo "Current crontab:"
crontab -l | grep -E "CRON_TZ|kinopois" || true
