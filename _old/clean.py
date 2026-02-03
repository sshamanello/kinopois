import csv

INPUT = "movies.csv"
OUTPUT = "movies_clean.csv"

with open(INPUT, "r", encoding="utf-8-sig") as f_in, \
     open(OUTPUT, "w", newline="", encoding="utf-8-sig") as f_out:
    reader = csv.DictReader(f_in, delimiter=";")
    fieldnames = reader.fieldnames + ["primary_genre"]
    writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter=";")
    writer.writeheader()

    for row in reader:
        poster_file = row.get("poster_file", "").strip()
        genres = row.get("genres", "").strip()
        title = row.get("title", "").strip()

        if not poster_file or not genres:
            continue  # нам нужны только фильмы с постером и жанром

        # первый жанр из строки "боевик, триллер"
        primary_genre = genres.split(",")[0].strip()

        row["primary_genre"] = primary_genre
        writer.writerow(row)

        print(f"Оставил: {title} [{primary_genre}]")
