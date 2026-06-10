# Deployment

## Docker

```bash
docker compose build
docker compose run --rm kinopois-prepare run-base-pipeline --limit 200
docker compose up -d kinopois-autopilot
```

`run-base-pipeline` writes publishable rows directly into `kinopois_pins`; it no longer depends on `pins.csv` as an intermediate queue handoff.

## Cron

```bash
bash deploy/cron-setup.sh
```

`data/` and `credentials/` are mounted volumes and should stay outside the image.

## Logs

```bash
# Application logs (rotated, 10MB x 5)
tail -f data/logs/kinopois.log

# Structured audit events (JSONL)
tail -f data/logs/events.log

# Docker logs
docker compose logs -f kinopois-autopilot
```