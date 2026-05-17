#!/bin/bash
# Setup cron job for kinopois on Linux VPS.
# Run once after cloning: bash deploy/cron-setup.sh

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$REPO_DIR/data/kinopois-cron.log"
CRON_HOUR="${CRON_HOUR:-9}"   # default: 9:00 every day

CRON_CMD="cd $REPO_DIR && docker compose run --rm kinopois-prepare >> $LOG_FILE 2>&1"
CRON_LINE="0 $CRON_HOUR * * * $CRON_CMD"

# Add to crontab if not already there
( crontab -l 2>/dev/null | grep -v "kinopois"; echo "$CRON_LINE" ) | crontab -

echo "Cron job set: runs at ${CRON_HOUR}:00 every day"
echo "Logs: $LOG_FILE"
echo ""
echo "Current crontab:"
crontab -l | grep kinopois
