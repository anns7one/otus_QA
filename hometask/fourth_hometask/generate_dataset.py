"""Генерация базы знаний по теории тестирования моделью llama3.2 в Docker.

Что делает скрипт:
  1. берёт список из 10 подтем теории тестирования;
  2. для каждой подтемы просит Ollama написать текст ~500 символов;
  3. сохраняет все тексты в dataset/knowledge_base.json

Запуск:  python generate_dataset.py
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11436/api/generate"
MODEL = "llama3.2"

HERE = Path(__file__).resolve().parent
OUTPUT_FILE = HERE / "dataset" / "knowledge_base.json"

TOPICS = [
    "Принципы тестирования (семь принципов)",
    "Фундаментальный процесс тестирования: планирование, анализ, дизайн, выполнение, завершение",
    "Уровни тестирования: модульное, интеграционное, системное, приёмочное",
    "Виды тестирования: функциональное, нефункциональное, белый и чёрный ящик",
    "Тестирование методом чёрного ящика: эквивалентное разбиение",
    "Граничные значения (boundary value analysis)",
    "Тестирование методом белого ящика: покрытие кода",
    "Тест-дизайн техники: таблицы решений и диаграммы состояний",
    "Статическое тестирование и ревью",
    "Управление тестированием: тест-планы и оценка рисков",
]


def ask_model(prompt: str) -> str:
    """Отправляет запрос в Ollama и возвращает ответ модели."""
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.4,
            "num_predict": 350,   # с запасом под ~500 символов на русском
        },
    }).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))["response"]
    except urllib.error.URLError as error:
        print("Не удалось достучаться до Ollama в контейнере.")
        print(f"  Причина: {error}")
        print("  Проверьте, что контейнер запущен командой docker ps")
        sys.exit(1)


def build_prompt(topic: str) -> str:
    return (
        f"Напиши текст на русском языке объёмом около 500 символов на тему "
        f"тестирования ПО: «{topic}». Пиши только сам текст, без заголовка, "
        f"без вступления и без markdown-разметки.Опирайся в ответе на силлабус IQSTB Fundation level"
    )


def main() -> None:
    documents = []

    for i, topic in enumerate(TOPICS, start=1):
        print(f"[{i}/{len(TOPICS)}] Генерирую текст: {topic}")
        text = ask_model(build_prompt(topic))
        documents.append({"id": i, "title": topic, "text": text.strip()})

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(documents, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nСохранено: {OUTPUT_FILE.relative_to(HERE)}")
    print(f"Документов: {len(documents)}")


if __name__ == "__main__":
    main()