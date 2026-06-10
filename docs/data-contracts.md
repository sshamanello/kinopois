# Data Contracts

## CSV rules

- delimiter: `;`
- encoding: `utf-8-sig`

## Pin rows

The exported `pins.csv` is now an optional snapshot. The canonical runtime queue is the Postgres `kinopois_pins` table.

## Pin row fields (27 columns)

```
id; image_url; poster_url; title; original_title; year; rating; genres;
primary_genre; kp_url; source_type; description; keywords; category;
board; board_id; status; created_at; posted_at; notes;
public_image_url; remote_image_path; vds_upload_status;
uploaded_at; publish_status; published_at; error_reason
```

## Important invariants

- `kp_id` is normalized to a clean integer string
- `rating` is accepted only when `0 < rating <= 10`
- cleaned rows must have `kp_id`, `title`, and `primary_genre`
- `movies_clean.csv` field names come from the cleaned row keys and should not append `primary_genre` twice

## Postgres queue

The `kinopois_pins` table is the single source of truth for publish state.
Key columns for n8n workflow:
- `publish_status = 'ready'` — row is ready for publishing
- `vds_upload_status = 'uploaded'` — image is available on the server
- `posted = 'TRUE'` — successfully published
- `pin_id` — Pinterest pin ID after publishing