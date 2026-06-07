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
kinopois queue-sync
kinopois run-prod --limit 200 --max-per-genre 1
```

## Autopilot

```bash
kinopois autopilot-once
kinopois autopilot
```
