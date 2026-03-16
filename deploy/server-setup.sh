#!/bin/bash
# One-time server setup: install Docker, clone repo, configure .env
# Run as root or with sudo on a fresh Ubuntu/Debian VPS.
# Usage: bash deploy/server-setup.sh

set -e

echo "=== Installing Docker ==="
apt-get update -q
apt-get install -y docker.io docker-compose-plugin
systemctl enable --now docker

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. Clone or upload this repo to the server"
echo "  2. Copy .env.example to .env and fill in all values:"
echo "       KINOPOISK_API_KEY=..."
echo "       GOOGLE_SHEETS_ID=..."
echo "       GOOGLE_CREDS_FILE=credentials/google-service-account.json"
echo "  3. Put your Google service account JSON at credentials/google-service-account.json"
echo "  4. Build the image:"
echo "       docker compose build"
echo "  5. Test a single run:"
echo "       docker compose run --rm kinopois run-pins --limit 10 --sync-sheets"
echo "  6. Set up cron (runs at 9:00 daily):"
echo "       bash deploy/cron-setup.sh"
