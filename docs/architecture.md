# Architecture

`kinopois` is split into three practical stages:

1. `download/` fetches raw movie data and posters from Kinopoisk
2. `processing/` cleans rows, builds poster collages or framed assets, and syncs them to the local cache DB
3. `publishing/` builds Pinterest rows, writes them to Postgres, and drives the n8n/autopilot layer

## Data flow

```text
Kinopoisk.dev API
  -> data/cache/movies.csv (optional snapshot)
  -> SQLite `movies_raw` / `movies_clean` / `collages` (cache)
  -> Postgres `kinopois_pins`
  -> n8n / autopilot / Pinterest API
```

The collage pipeline is independent from the pin-export pipeline.
