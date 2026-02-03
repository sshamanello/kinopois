import csv
import os
from datetime import datetime

COLLAGES_CSV = "collages_with_titles.csv"
OUTPUT_CSV = "pins.csv"

BASE_IMAGE_URL = "https://sshamanello.ru/collages"  # поменяй под себя
BOARD_NAME = "Фильмы на вечер"
BOARD_ID = "ВАШ_BOARD_ID"
BOT_URL = "https://t.me/TopTrailer82Bot"

TITLES = [
    "4 мелодрамы, которые хочется смотреть запоем",
    "4 мелодрамы для уютного вечера вдвоём",
    "4 мелодрамы, оставляющие тёплое послевкусие",
    "4 мелодрамы, которые цепляют с первых минут",
    "4 мелодрамы, чтобы погрузиться в чувства по полной",
    "4 детектива, от которых невозможно оторваться",
    "4 комедии, чтобы поднять себе настроение",
    "4 комедии, которые реально смешные",
    "4 комедии на вечер, когда хочется просто расслабиться",
    "4 комедии, которые заставят улыбаться до конца",
    "4 триллера, которые держат в напряжении каждый кадр",
    "4 триллера, после которых сложно уснуть",
    "4 триллера с мощными сюжетными твистами",
    "4 триллера, которые пробирают до мурашек",
    "4 триллера для тех, кто любит настоящий саспенс",
    "4 драмы, которые бьют в самое сердце",
    "4 драмы, оставляющие долгий след в голове",
    "4 драмы, которые хочется обсуждать",
    "4 драмы, основанные на сильных историях",
    "4 драмы, которые заставляют задуматься",
    "4 эмоциональные драмы на вечер",
    "4 драмы, которые трогают до глубины души",
    "4 драмы, которые невозможно забыть",
    "4 драмы для тех, кто любит сильные переживания",
    "4 драмы, которые цепляют с первых минут",
    "4 мощные драмы, которые смотрятся на одном дыхании",
    "4 драмы, которые раскрывают человеческие истории",
    "4 глубокие драмы для вдумчивого просмотра",
    "4 документалки, которые реально расширяют кругозор",
    "4 документальных фильма, от которых сложно отвести взгляд",
    "4 документалки с сильным посылом",
    "4 документалки, которые нужно увидеть каждому",
    "4 документальных фильма, которые вдохновляют",
    "4 боевика, где действие начинается сразу",
    "4 боевика для заряда адреналином",
    "4 аниме, которые стоит посмотреть новичку",
    "4 аниме, которые цепляют с первой серии",
    "4 атмосферных аниме для вечера",
    "4 аниме, которые тебя удивят",
    "4 мультфильма для идеального семейного вечера",
    "4 мультфильма, которые создают уютное настроение",
]

rows = []
with open(COLLAGES_CSV, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        rows.append(row)

count = min(len(rows), len(TITLES))
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f_out:
    writer = csv.writer(f_out, delimiter=";")
    writer.writerow([
        "id",
        "image_url",
        "title",
        "description",
        "keywords",
        "category",
        "board",
        "board_id",
        "status",
        "created_at",
        "posted_at",
        "notes",
    ])

    for i in range(count):
        c = rows[i]
        genre = (c.get("genre") or "").strip()
        collage_file = (c.get("collage_file") or "").strip()
        film1 = (c.get("film1") or "").strip()
        film2 = (c.get("film2") or "").strip()
        film3 = (c.get("film3") or "").strip()
        film4 = (c.get("film4") or "").strip()

        title = TITLES[i]
        filename = os.path.basename(collage_file)
        image_url = f"{BASE_IMAGE_URL}/{filename}"

        films_list = ", ".join([f for f in [film1, film2, film3, film4] if f])

        description = (
            f"{title}. Фильмы в подборке: {films_list}.\n"
            f"Напиши нашему кино-боту в Telegram, чтобы быстро найти фильмы под настроение: {BOT_URL}"
        )

        keywords = f"фильмы,{genre},подборка,что посмотреть,кино на вечер"

        writer.writerow([
            i + 1,
            image_url,
            title,
            description,
            keywords,
            "Фильмы",
            BOARD_NAME,
            BOARD_ID,
            "pending",
            now_str,
            "",
            "",
        ])

print(f"Готово: {OUTPUT_CSV}, строк: {count}")
