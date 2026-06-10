#!/usr/bin/env python3
"""
Конвертер экспорта Claude.ai в Obsidian-формат
Отсеивает мусор, создаёт связи, структурирует по датам
"""

import json
import os
import re
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import shutil

# Пути
EXPORT_DIR = Path("/Users/nick/Downloads/0476be81858bd4754d2c93d8f0efba2017f28da344843799a1468c4ceb40d817-2026-06-05-08-59-20-a475746d3b9a4033b248554c5f494d95")
OUTPUT_DIR = Path("/Users/nick/Downloads/claude_obsidian_export")

# Фильтры мусора
MIN_MESSAGE_LENGTH = 50  # Минимальная длина сообщения для сохранения
SKIP_SYSTEM_PATTERNS = [
    r'^System\s*:', r'^system\s*:', r'^System message',
    r'^\s*$',  # Пустые сообщения
]
SKIP_CONTENT_PATTERNS = [
    r'^```\s*$',  # Только кодовые блоки без содержимого
]

def sanitize_filename(name: str) -> str:
    """Очистка имени файла"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100]  # Ограничение длины

def extract_title(chat: dict) -> str:
    """Извлечение заголовка из чата"""
    # Пробуем найти в mapping
    mapping = chat.get('mapping', {})

    # Ищем первое сообщение пользователя
    for node_id, node in mapping.items():
        msg = node.get('message')
        if msg and msg.get('author', {}).get('role') == 'user':
            content = msg.get('content', {})
            parts = content.get('parts', [])
            if parts:
                text = parts[0] if isinstance(parts[0], str) else str(parts[0])
                # Берём первые 50 символов
                title = text.strip()[:50].replace('\n', ' ')
                if len(title) > 10:
                    return title

    # Фолбэк — create_time
    ts = chat.get('create_time', 0)
    if ts:
        return f"Chat_{datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M')}"
    return f"Chat_{chat.get('id', 'unknown')[:8]}"

def extract_tags(text: str) -> list:
    """Извлечение тегов из текста"""
    tags = set()

    # Код/программирование
    if any(k in text.lower() for k in ['python', 'javascript', 'code', 'programming', 'функция', 'код', 'script', 'api', 'баг', 'error', 'debug']):
        tags.add('coding')

    # AI/ML
    if any(k in text.lower() for k in ['ai', 'ml', 'model', 'neural', 'gpt', 'claude', 'модель', 'нейросеть', 'machine learning']):
        tags.add('ai-ml')

    # Проекты
    if any(k in text.lower() for k in ['project', 'проект', 'app', 'application', 'система', 'architecture', 'архитектура']):
        tags.add('projects')

    # Дизайн/UI
    if any(k in text.lower() for k in ['design', 'ui', 'ux', 'interface', 'дизайн', 'интерфейс', 'figma', 'css']):
        tags.add('design')

    # Бизнес/продукт
    if any(k in text.lower() for k in ['business', 'startup', 'product', 'бизнес', 'продукт', 'стратегия', 'strategy', 'marketing']):
        tags.add('business')

    # Личное/жизнь
    if any(k in text.lower() for k in ['life', 'personal', 'health', 'философия', 'психология', 'relationship', 'семья']):
        tags.add('personal')

    # Творчество
    if any(k in text.lower() for k in ['write', 'story', 'creative', 'art', 'писать', 'творчество', 'книга', 'рассказ']):
        tags.add('creative')

    # Обучение
    if any(k in text.lower() for k in ['learn', 'study', 'tutorial', 'обучение', 'курс', 'изучить', 'how to']):
        tags.add('learning')

    # Данные
    if any(k in text.lower() for k in ['data', 'database', 'sql', 'postgres', 'json', 'csv', 'анализ данных']):
        tags.add('data')

    # Инфраструктура/DevOps
    if any(k in text.lower() for k in ['docker', 'kubernetes', 'deploy', 'server', 'infra', 'devops', 'ci/cd', 'github', 'git']):
        tags.add('devops')

    return sorted(tags)

def is_junk_message(msg: dict) -> bool:
    """Проверка, является ли сообщение мусором"""
    if not msg:
        return True

    content = msg.get('content', {})
    parts = content.get('parts', [])

    if not parts:
        return True

    text = parts[0] if isinstance(parts[0], str) else str(parts[0])

    # Слишком короткое
    if len(text.strip()) < MIN_MESSAGE_LENGTH:
        return True

    # Паттерны мусора
    for pattern in SKIP_SYSTEM_PATTERNS:
        if re.match(pattern, text.strip(), re.I):
            return True

    return False

def format_message(msg: dict, is_user: bool) -> str:
    """Форматирование сообщения в Markdown"""
    content = msg.get('content', {})
    parts = content.get('content_type', 'text')

    if parts == 'multimodal_text':
        # Обработка вложений
        text_parts = []
        for part in content.get('parts', []):
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and part.get('content_type') == 'image_asset_pointer':
                # Ссылка на изображение
                asset_id = part.get('asset_pointer', '').replace('file-service://', '')
                text_parts.append(f"![[{asset_id}]]")
        text = '\n'.join(text_parts)
    else:
        parts = content.get('parts', [])
        text = parts[0] if parts and isinstance(parts[0], str) else str(parts[0]) if parts else ''

    # Экранирование для Markdown
    text = text.replace('```', '\`\`\`')

    # Роль
    role = "**You**" if is_user else "**Claude**"

    return f"\n{role}:\n{text}\n"

def process_chat(chat: dict) -> dict:
    """Обработка одного чата"""
    chat_id = chat.get('id', 'unknown')
    create_time = chat.get('create_time', 0)
    update_time = chat.get('update_time', 0)

    if not create_time:
        return None

    date = datetime.fromtimestamp(create_time)

    # Извлекаем сообщения
    messages = []
    mapping = chat.get('mapping', {})

    # Обходим дерево сообщений
    current_node = chat.get('current_node')
    if not current_node:
        return None

    # Собираем цепочку от текущего узла к корню
    node_chain = []
    node_id = current_node
    visited = set()

    while node_id and node_id not in visited:
        visited.add(node_id)
        node = mapping.get(node_id, {})
        msg = node.get('message')
        if msg and not is_junk_message(msg):
            node_chain.append((node_id, msg))
        node_id = node.get('parent')

    # Реверсируем для хронологического порядка
    node_chain.reverse()

    if len(node_chain) < 2:  # Слишком короткий чат
        return None

    # Форматируем сообщения
    all_text = []
    formatted_messages = []

    for node_id, msg in node_chain:
        role = msg.get('author', {}).get('role', 'unknown')
        is_user = role == 'user'

        content = msg.get('content', {})
        parts = content.get('parts', [])
        text = ''
        if parts:
            if isinstance(parts[0], str):
                text = parts[0]
            else:
                text = str(parts[0])

        all_text.append(text)
        formatted_messages.append(format_message(msg, is_user))

    full_text = ' '.join(all_text)
    tags = extract_tags(full_text)
    title = extract_title(chat)

    # Генерация имени файла
    date_str = date.strftime('%Y-%m-%d')
    safe_title = sanitize_filename(title)
    filename = f"{date_str}_{safe_title}.md"

    return {
        'id': chat_id,
        'title': title,
        'filename': filename,
        'date': date,
        'date_str': date_str,
        'tags': tags,
        'messages': formatted_messages,
        'word_count': len(full_text.split()),
        'message_count': len(formatted_messages),
    }

def create_obsidian_note(chat_data: dict) -> str:
    """Создание Obsidian-заметки"""
    tags_str = ' '.join([f"#{tag}" for tag in chat_data['tags']])

    frontmatter = f"""---
id: {chat_data['id']}
date: {chat_data['date'].isoformat()}
title: {chat_data['title']}
tags: {tags_str}
word_count: {chat_data['word_count']}
message_count: {chat_data['message_count']}
---

# {chat_data['title']}

**Дата:** [[{chat_data['date_str']}|{chat_data['date_str']}]]
**Теги:** {' '.join([f"[[{tag}]]" for tag in chat_data['tags']])}

---

"""

    content = '\n'.join(chat_data['messages'])

    # Добавляем ссылки на связанные заметки (по тегам)
    related = f"\n\n---\n\n## Связанные темы\n\nСм. также: {' '.join([f"[[{tag}]]" for tag in chat_data['tags']])}\n"

    return frontmatter + content + related

def process_all_conversations():
    """Обработка всех файлов conversations"""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Создаём структуру папок
    (OUTPUT_DIR / "daily").mkdir(exist_ok=True)
    (OUTPUT_DIR / "tags").mkdir(exist_ok=True)
    (OUTPUT_DIR / "attachments").mkdir(exist_ok=True)

    all_chats = []
    tag_index = defaultdict(list)
    date_index = defaultdict(list)

    # Обрабатываем все JSON файлы
    json_files = sorted(EXPORT_DIR.glob("conversations-*.json"))
    print(f"Найдено {len(json_files)} файлов для обработки")

    for i, json_file in enumerate(json_files):
        print(f"Обработка {i+1}/{len(json_files)}: {json_file.name}")

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for chat in data:
                processed = process_chat(chat)
                if processed:
                    all_chats.append(processed)

                    # Индексация по тегам
                    for tag in processed['tags']:
                        tag_index[tag].append(processed)

                    # Индексация по датам
                    date_index[processed['date_str']].append(processed)

        except Exception as e:
            print(f"Ошибка при обработке {json_file}: {e}")

    print(f"\nОбработано чатов: {len(all_chats)}")

    # Создаём заметки
    print("\nСоздание Obsidian-заметок...")

    for chat in all_chats:
        # Сохраняем в папку daily
        note_path = OUTPUT_DIR / "daily" / chat['filename']
        note_content = create_obsidian_note(chat)

        # Проверка на дубликаты
        counter = 1
        original_path = note_path
        while note_path.exists():
            stem = original_path.stem
            note_path = OUTPUT_DIR / "daily" / f"{stem}_{counter}.md"
            counter += 1

        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(note_content)

    # Создаём MOC (Map of Content) для тегов
    print("Создание MOC для тегов...")
    for tag, chats in tag_index.items():
        tag_moc = f"""---
title: {tag}
type: MOC
tags: meta
---

# {tag}

Количество чатов: {len(chats)}

## Чаты по этой теме

"""
        for chat in sorted(chats, key=lambda x: x['date'], reverse=True):
            tag_moc += f"- [[{chat['filename'].replace('.md', '')}|{chat['title']}]] — {chat['date_str']}\n"

        with open(OUTPUT_DIR / "tags" / f"{tag}.md", 'w', encoding='utf-8') as f:
            f.write(tag_moc)

    # Создаём MOC для дат (ежедневные заметки)
    print("Создание ежедневных заметок...")
    for date_str, chats in date_index.items():
        daily_note = f"""---
date: {date_str}
type: daily
tags: daily
---

# {date_str}

Количество чатов: {len(chats)}

## Чаты за этот день

"""
        for chat in sorted(chats, key=lambda x: x['date']):
            daily_note += f"- [[{chat['filename'].replace('.md', '')}|{chat['title']}]]\n"

        with open(OUTPUT_DIR / "daily" / f"{date_str}.md", 'w', encoding='utf-8') as f:
            f.write(daily_note)

    # Главный индекс
    print("Создание главного индекса...")
    index = f"""---
title: Claude Chats Archive
type: index
tags: meta
---

# Архив чатов Claude

**Всего чатов:** {len(all_chats)}
**Дата экспорта:** {datetime.now().strftime('%Y-%m-%d')}

## Навигация по тегам

"""
    for tag in sorted(tag_index.keys()):
        index += f"- [[{tag}]] — {len(tag_index[tag])} чатов\n"

    index += "\n## Последние чаты\n\n"
    for chat in sorted(all_chats, key=lambda x: x['date'], reverse=True)[:50]:
        index += f"- [[{chat['filename'].replace('.md', '')}|{chat['title']}]] — {chat['date_str']}\n"

    with open(OUTPUT_DIR / "00_Index.md", 'w', encoding='utf-8') as f:
        f.write(index)

    # Копируем вложения если есть
    attachments_dir = EXPORT_DIR / "attachments"
    if attachments_dir.exists():
        print("Копирование вложений...")
        for f in attachments_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, OUTPUT_DIR / "attachments" / f.name)

    print(f"\n✅ Готово! Заметки сохранены в: {OUTPUT_DIR}")
    print(f"📊 Статистика:")
    print(f"   - Всего чатов: {len(all_chats)}")
    print(f"   - Уникальных тегов: {len(tag_index)}")
    print(f"   - Уникальных дат: {len(date_index)}")

if __name__ == "__main__":
    process_all_conversations()
