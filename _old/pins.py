import csv
import os
import re
from collections import defaultdict

MOVIES_CSV = "movies_clean.csv"
OUTPUT_CSV = "collages_with_titles.csv"
COLLAGES_DIR = "collages"  # где лежат готовые .jpg

TILE_W = 500
TILE_H = 750  # просто для инфы, тут не нужен

def safe_name(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "_", s)
    return s.strip("_") or "genre"

# 1. Читаем фильмы и группируем по жанру, сортируем по рейтингу
groups = defaultdict(list)

with open(MOVIES_CSV, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        genre = (row.get("primary_genre") or "").strip()
        poster_file = (row.get("poster_file") or "").strip()
        title = (row.get("title") or "").strip()
        rating_raw = (row.get("rating_kp") or "").strip()

        if not genre or not poster_file:
            continue
        if not os.path.exists(poster_file):
            continue

        rating_clean = rating_raw.replace(",", ".")
        try:
            rating_value = float(rating_clean)
        except:
            rating_value = 0.0

        groups[genre].append({
            "title": title,
            "poster_file": poster_file,
            "rating": rating_value,
        })

if not groups:
    raise RuntimeError("Не нашли ни одного фильма. Проверь movies_clean.csv и пути poster_file.")

# 2. Собираем мету по коллажам в том же порядке, как в make_collages.py
rows_out = []

for genre, films in groups.items():
    if len(films) < 4:
        continue

    films_sorted = sorted(films, key=lambda x: -x["rating"])
    safe_genre = safe_name(genre)

    collage_index = 1
    for i in range(0, len(films_sorted), 4):
        batch = films_sorted[i:i+4]
        if len(batch) < 4:
            break

        collage_file = f"{safe_genre}_{collage_index:02d}.jpg"
        collage_path = os.path.join(COLLAGES_DIR, collage_file)
        if not os.path.exists(collage_path):
            # если по какой-то причине картинки нет, пропускаем
            continue

        rows_out.append({
            "genre": genre,
            "collage_file": collage_file,
            "film1": batch[0]["title"],
            "film2": batch[1]["title"],
            "film3": batch[2]["title"],
            "film4": batch[3]["title"],
        })

        collage_index += 1

# 3. Пишем collages_with_titles.csv
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f_out:
    writer = csv.writer(f_out, delimiter=";")
    writer.writerow(["genre", "collage_file", "film1", "film2", "film3", "film4"])
    for row in rows_out:
        writer.writerow([
            row["genre"],
            row["collage_file"],
            row["film1"],
            row["film2"],
            row["film3"],
            row["film4"],
        ])

print(f"Готово: {OUTPUT_CSV}, строк: {len(rows_out)}")
