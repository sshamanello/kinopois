import csv
import os
import re
import subprocess
from collections import defaultdict

# ==== НАСТРОЙКИ ====

INPUT_CSV = "movies_clean.csv"   # входной файл с фильмами
OUTPUT_DIR = "collages"          # куда класть коллажи
COLLAGES_CSV = "collages.csv"    # таблица с данными о коллажах

TILE_W = 500                     # ширина одной плитки
TILE_H = 750                     # высота одной плитки

MAX_COLLAGES_PER_GENRE = None    # None = все возможные; или число, напр. 5

BOT_TAG = "@TopTrailer82Bot"                    # подпись НА КАРТИНКЕ (замени)
BOT_LINK = "https://t.me/TopTrailer82Bot"       # ссылка для Pinterest/CSV

# ================== ВСПОМОГАТЕЛЬНОЕ ==================


def safe_name(s: str) -> str:
    """Очистка жанра для имени файла."""
    s = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "_", s)
    return s.strip("_") or "genre"


# ================== ЧТЕНИЕ ФИЛЬМОВ ==================

groups = defaultdict(list)

if not os.path.exists(INPUT_CSV):
    raise FileNotFoundError(f"Не найден {INPUT_CSV} в {os.getcwd()}")

with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        genre = (row.get("primary_genre") or "").strip()
        poster_file = (row.get("poster_file") or "").strip()
        title = (row.get("title") or "").strip()
        rating_raw = (row.get("rating_kp") or "").strip()

        if not genre or not poster_file:
            continue
        if not os.path.exists(poster_file):
            # постера физически нет -> пропускаем
            continue

        # рейтинг: "6,00" -> 6.0
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
    raise RuntimeError("В группах пусто. Проверь movies_clean.csv и пути poster_file.")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ================== ФУНКЦИЯ СОЗДАНИЯ КОЛЛАЖА ==================


def make_collage(batch, genre, index):
    """
    batch: список из 4 dict'ов: {title, poster_file, rating}
    genre: жанр
    index: номер коллажа для этого жанра (1, 2, 3, ...)
    """
    p1 = batch[0]["poster_file"]
    p2 = batch[1]["poster_file"]
    p3 = batch[2]["poster_file"]
    p4 = batch[3]["poster_file"]

    safe_genre = safe_name(genre)
    out_name = f"{safe_genre}_{index:02d}.jpg"
    out_path = os.path.join(OUTPUT_DIR, out_name)

    # текст на картинке — только латиница, чтобы не ловить проблемы шрифта
    overlay_text = BOT_TAG  # например "@your_telegram_bot"

    # 2x2 коллаж + плашка + текст
    filter_complex = (
        f"[0:v] scale={TILE_W}:{TILE_H} [a];"
        f"[1:v] scale={TILE_W}:{TILE_H} [b];"
        f"[2:v] scale={TILE_W}:{TILE_H} [c];"
        f"[3:v] scale={TILE_W}:{TILE_H} [d];"
        f"[a][b][c][d]xstack=inputs=4:layout=0_0|{TILE_W}_0|0_{TILE_H}|{TILE_W}_{TILE_H},"
        # полупрозрачная чёрная плашка снизу
        f"drawbox=x=0:y={TILE_H*2-80}:w={TILE_W*2}:h=80:color=black@0.5:t=fill,"
        # подпись бота по центру плашки
        f"drawtext=text='{overlay_text}':fontcolor=white:fontsize=32:x=(w-text_w)/2:y={TILE_H*2-60}"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", p1,
        "-i", p2,
        "-i", p3,
        "-i", p4,
        "-filter_complex", filter_complex,
        out_path,
    ]

    subprocess.run(cmd, check=True)

    return out_name  # вернём имя файла коллажа


# ================== ГЕНЕРАЦИЯ КОЛЛАЖЕЙ + CSV ==================

total = 0

with open(COLLAGES_CSV, "w", newline="", encoding="utf-8-sig") as f_csv:
    writer = csv.writer(f_csv, delimiter=";")
    # базовые поля для импортов и нейросетевого генератора текстов
    writer.writerow([
        "genre",
        "collage_file",
        "link",
    ])

    for genre, films in groups.items():
        if len(films) < 4:
            continue

        # сортировка по рейтингу (от большего к меньшему)
        films_sorted = sorted(films, key=lambda x: -x["rating"])

        collage_index = 1
        for i in range(0, len(films_sorted), 4):
            batch = films_sorted[i:i+4]
            if len(batch) < 4:
                break

            if MAX_COLLAGES_PER_GENRE is not None and collage_index > MAX_COLLAGES_PER_GENRE:
                break

            collage_file = make_collage(batch, genre, collage_index)

            # строка в CSV
            writer.writerow([
                genre,
                collage_file,
                BOT_LINK,
            ])

            collage_index += 1
            total += 1

print(f"Готово. Создано коллажей: {total}")
print(f"Папка с картинками: {os.path.abspath(OUTPUT_DIR)}")
print(f"Таблица с данными:  {os.path.abspath(COLLAGES_CSV)}")
