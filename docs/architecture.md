# Architecture

`kinopois` is split into three practical stages:

1. `download/` fetches raw movie data and posters from Kinopoisk
2. `processing/` cleans CSV rows and builds poster collages or framed assets
3. `publishing/` exports Pinterest rows, runs the local queue, and drives the n8n/autopilot layer

## Data flow

```text
Kinopoisk.dev API
  -> data/cache/movies.csv
  -> data/cache/movies_clean.csv
  -> data/cache/pins.csv
  -> SQLite queue / n8n / Pinterest API
```

The collage pipeline is independent from the pin-export pipeline.
