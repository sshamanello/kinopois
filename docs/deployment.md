# Deployment

## Docker

```bash
docker compose build
docker compose run --rm kinopois-prepare run-base-pipeline --limit 200
docker compose up -d kinopois-autopilot
```

## Cron

```bash
bash deploy/cron-setup.sh
```

`data/` and `credentials/` are mounted volumes and should stay outside the image.
