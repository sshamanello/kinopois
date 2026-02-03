import os
import csv
import requests

API_KEY = "CTPQG3K-9584QAC-G6GB6EF-S97FR8K"

# === БАЗОВАЯ ПАПКА = где лежит сам скрипт ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

POSTERS_DIR = os.path.join(BASE_DIR, "posters")
CSV_FILE = os.path.join(BASE_DIR, "movies.csv")

# Сколько фильмов ХОТИМ В ИТОГЕ (с постером!)
MOVIES_LIMIT = 200
PAGE_SIZE = 50  # можно оставить 50, просто быстро насобираем 10 штук

os.makedirs(POSTERS_DIR, exist_ok=True)


def fetch_movies(page: int, limit: int):
    url = "https://api.kinopoisk.dev/v1.4/movie"
    headers = {
        "X-API-KEY": API_KEY,
        "accept": "application/json",
    }
    params = {
        "page": page,
        "limit": limit,
        # можно ужесточить выборку, напр. по рейтингу/годам
        "rating.kp": "6-10",
        "year": "2000-2025",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("docs", []), data.get("pages", 1)


def download_image(url: str, filename: str):
    resp = requests.get(url, stream=True, timeout=20)
    resp.raise_for_status()
    path = os.path.join(POSTERS_DIR, filename)
    with open(path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    return path


def main():
    collected = 0
    page = 1

    # ВАЖНО: encoding="utf-8-sig" -> Excel нормально покажет кириллицу
    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "kp_id",
            "title",
            "original_title",
            "year",
            "genres",
            "rating_kp",
            "poster_url",
            "poster_file",
        ])

        while collected < MOVIES_LIMIT:
            movies, total_pages = fetch_movies(page, PAGE_SIZE)
            if not movies:
                break

            for m in movies:
                if collected >= MOVIES_LIMIT:
                    break

                kp_id = m.get("id")
                title = m.get("name") or ""
                original_title = (
                    m.get("alternativeName")
                    or m.get("enName")
                    or ""
                )
                year = m.get("year") or ""
                rating = None
                if isinstance(m.get("rating"), dict):
                    rating = m["rating"].get("kp")

                genres_list = m.get("genres") or []
                genres_names = ", ".join(
                    g.get("name") for g in genres_list if g.get("name")
                )

                # === БЕРЁМ ПОСТЕР ПРЯМО ИЗ movie.poster ===
                poster_data = m.get("poster") or {}
                poster_preview_url = poster_data.get("previewUrl") or poster_data.get("url")
                poster_full_url = poster_data.get("url")

                # === ЕСЛИ НЕТ ПОСТЕРА – ПРОПУСКАЕМ ФИЛЬМ ===
                if not poster_preview_url:
                    # print(f"Пропускаю {title} — нет постера")
                    continue

                # === СКАЧИВАЕМ ТОЛЬКО ЕСЛИ ЕСТЬ URL ===
                poster_file_path = ""
                try:
                    ext = ".jpg"
                    poster_filename = f"{kp_id}{ext}"
                    poster_file_path = download_image(poster_preview_url, poster_filename)
                except Exception as e:
                    print(f"Не смог скачать постер для {kp_id} ({title}): {e}")
                    # если постер не скачался – тоже пропускаем, нам важны только с реальной картинкой
                    continue

                writer.writerow([
                    kp_id,
                    title,
                    original_title,
                    year,
                    genres_names,
                    rating,
                    poster_full_url or poster_preview_url or "",
                    poster_file_path,
                ])

                collected += 1
                print(f"[{collected}/{MOVIES_LIMIT}] {title} ({year})")

            page += 1
            if page > total_pages:
                break


if __name__ == "__main__":
    main()
