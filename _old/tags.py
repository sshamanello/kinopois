import csv
from collections import defaultdict

INPUT = "movies_clean.csv"

groups = defaultdict(list)

with open(INPUT, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        genre = (row.get("primary_genre") or "").strip()
        poster_file = (row.get("poster_file") or "").strip()
        title = (row.get("title") or "").strip()
        rating_raw = (row.get("rating_kp") or "").strip()

        # пропускаем строки без жанра или без постера
        if not genre or not poster_file:
            continue

        # приводим рейтинг к float, учитывая запятую в числе
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

# пример: выводим первые 2 коллажа для одного жанра
target_genre = "триллер"  # здесь меняешь на нужный жанр из таблицы

if target_genre not in groups:
    print(f"Жанр '{target_genre}' не найден в данных.")
else:
    films = sorted(groups[target_genre], key=lambda x: -x["rating"])
    print(f"Найдено {len(films)} фильмов жанра {target_genre}")

    # разбиваем по 4 фильма: первые 2 коллажа = максимум 8 фильмов
    for i in range(0, min(len(films), 8), 4):
        batch = films[i:i+4]
        if len(batch) < 4:
            break

        print(f"\nКоллаж #{i // 4 + 1}:")
        for film in batch:
            print(f"  {film['title']}  ->  {film['poster_file']}")
