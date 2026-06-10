# Data Contracts

## CSV rules

- delimiter: `;`
- encoding: `utf-8-sig`

## Pin rows

The exported `pins.csv` is now an optional snapshot. The canonical runtime queue is the Postgres `kinopois_pins` table.

## Important invariants

- `kp_id` is normalized to a clean integer string
- `rating` is accepted only when `0 < rating <= 10`
- cleaned rows must have `kp_id`, `title`, and `primary_genre`
- `movies_clean.csv` field names come from the cleaned row keys and should not append `primary_genre` twice
