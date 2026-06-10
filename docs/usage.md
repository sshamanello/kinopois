# Usage

## Download

```bash
kinopois download --limit 200
```

## Processing

```bash
kinopois process
kinopois collage --watermark "@YourBot" --max-per-genre 2
```

## Publishing

```bash
kinopois export-movie-pins
kinopois run-base-pipeline --limit 200
kinopois run-prod --limit 200 --max-per-genre 1
```

`export-movie-pins` remains a manual CSV export. The default publish pipeline writes straight into the Postgres queue consumed by n8n.

## Autopilot

```bash
kinopois autopilot-once
kinopois autopilot
```
