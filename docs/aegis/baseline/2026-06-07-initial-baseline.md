# Initial Baseline Snapshot

Date: 2026-06-07

## Current publish flow

- Movie data is downloaded and processed into CSV artifacts.
- `pins.csv` is exported from `movies_clean.csv`.
- `queue-sync` imports `pins.csv` into `kinopois_pins`.
- n8n publishes from `kinopois_pins`.

## Current invariants

- Published and failed rows must not be overwritten by later syncs.
- CSV files use `;` delimiter and UTF-8 BOM encoding.
- `kinopois_pins` is the live publish queue, but not yet the only write path.
