# ДЗ: Локальная RAG-генерация на Python 3

Локальная RAG-система (Retrieval-Augmented Generation) для ответов на вопросы
по теории тестирования. База знаний — 10 текстов, сгенерированных моделью
Ollama на основе официального стандарта ISTQB Foundation Level Syllabus v4.0.

## Что делает

1. `generate_dataset.py` — генерирует базу знаний (10 текстов ~500 символов
   по темам теории тестирования), сохраняет в `dataset/knowledge_base.json`.
2. `rag_generator.py` — интерактивный CLI: по вопросу пользователя находит
   релевантные документы через семантические эмбеддинги (косинусная
   близость), передаёт их модели как контекст и генерирует ответ.

## Требования

- Docker Desktop
- Python 3.10+
- Никаких pip-зависимостей — весь код на стандартной библиотеке
  (`urllib`, `json`, `math`, `pathlib`)

## Установка и запуск

1. Поднять Ollama в Docker:
   ```
   docker compose up -d
   ```
2. Скачать модели внутрь контейнера:
   ```
   docker exec ollama-hm4 ollama pull llama3.2
   docker exec ollama-hm4 ollama pull nomic-embed-text
   docker exec ollama-hm4 ollama list
   ```
3. Проверить, что Ollama отвечает:
   ```
   curl http://localhost:11436/api/tags
   ```
4. Сгенерировать базу знаний (можно пропустить — в репозитории уже есть готовый `dataset/knowledge_base.json`):
   ```
   python generate_dataset.py
   ```
5. Запустить RAG-генератор:
   ```
   python rag_generator.py
   ```
   Можно задавать вопросы по теории тестирования — для выхода из генерации ответ
   "нет" или "exit" на вопрос "Задать ещё один вопрос?".

## Пример работы

См. [example_dialog.md](example_dialog.md) — реальный диалог с системой.

## Структура файлов

```
fourth_hometask/
dataset/                # база знаний (10 текстов по теории тестирования)
  knowledge_base.json   # готовая база знаний, 10 документов
docker-compose.yml      # Ollama в Docker (порт 11436)
generate_dataset.py     # генерация базы знаний
rag_generator.py        # RAG-генератор (retrieval + generation)
example_dialog.md       # пример реального диалога
README.md
```