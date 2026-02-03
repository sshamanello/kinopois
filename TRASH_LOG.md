# Удаленные и перемещенные файлы

## Перемещено в `_old/` (резервная копия)

### Старые Python скрипты (заменены на модульную структуру)

| Файл | Описание | Замена |
|------|----------|--------|
| `kinoscraper.py` | Скачивание с Кинопоиска | `kinopois/scraper.py` + `kinopois/cli.py download` |
| `clean.py` | Очистка CSV | `kinopois/processor.py` + `kinopois/cli.py process` |
| `tags.py` | Группировка по жанрам | `kinopois/processor.py` |
| `make_collages.py` | Создание коллажей | `kinopois/collage.py` + `kinopois/cli.py collage` |
| `pins.py` | Экспорт для Pinterest | `kinopois/export.py` + `kinopois/cli.py export` |
| `pins_for_collage.py` | Метаданные коллажей | `kinopois/export.py` |

### Другие файлы

| Файл | Причина удаления |
|------|------------------|
| `pins.xlsx` | Генерируется из `pins.csv`, дублирование |
| `project_contents.txt` | Мусор (53KB дамп содержимого проекта) |

## Новая структура

```
kinopois/
├── kinopois/          # Основной пакет
│   ├── __init__.py
│   ├── cli.py        # CLI интерфейс
│   ├── config.py     # Конфигурация
│   ├── scraper.py    # API клиент
│   ├── processor.py  # Обработка данных
│   ├── collage.py    # Создание коллажей
│   ├── marker.py     # Водяные знаки
│   ├── export.py     # Экспорт
│   └── utils.py      # Утилиты
├── data/              # Данные
│   ├── posters/      # Постеры (перемещены из posters/)
│   ├── collages/     # Коллажи (перемещены из collages/)
│   └── cache/        # CSV файлы (перемещены из корня)
├── _old/             # Старые файлы (резерв)
├── tests/            # Тесты
├── .env.example      # Пример конфигурации
├── .gitignore
├── pyproject.toml    # Зависимости
└── README.md         # Документация
```

## Можно удалить полностью

После проверки работы новой структуры, папку `_old/` можно удалить:

```bash
rm -rf _old/
```

## CSV файлы (перемещены в data/cache/)

- `movies.csv` -> `data/cache/movies.csv`
- `movies_clean.csv` -> `data/cache/movies_clean.csv`
- `collages.csv` -> `data/cache/collages.csv`
- `collages_with_titles.csv` -> `data/cache/` (использовался при генерации)
- `pins.csv` -> `data/cache/pins.csv`
