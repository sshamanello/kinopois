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
kinopois pins --limit 200 --sync-queue
```

`export-movie-pins` remains a manual CSV export. The default publish pipeline writes straight into the Postgres queue consumed by n8n.

## Queue management

```bash
kinopois db-init                    # Initialize Postgres schema
kinopois db-sync-all                # Sync all CSVs -> SQLite + Postgres
kinopois db-stats                    # Show queue counts
kinopois queue-ready --limit 5      # Show ready jobs as JSON
kinopois queue-posted --job-id 1 --pin-id abc123
kinopois queue-failed --job-id 1 --error "API error"
```

## Autopilot

```bash
kinopois autopilot-once             # One tick (harvest + post slots)
kinopois autopilot                  # Daemon mode (runs forever)
```

## Interactive menu

```bash
kinopois                            # Launch TUI menu
kinopois menu                       # Same as above
```