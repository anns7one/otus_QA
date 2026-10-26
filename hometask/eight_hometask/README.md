# ДЗ8. Автотесты LLM на галлюцинации и качество ответов (Ollama + llama3)

Автотесты на pytest, которые проверяют модель `llama3` (через Ollama) по трём
направлениям: не выдумывает ли она факты (галлюцинации), даёт ли одинаковый
ответ на повторные запросы (согласованность), и правильно ли ведёт себя сам
REST API Ollama (корректные и ошибочные запросы).

## Стек

Python 3, pytest, requests, Docker, Ollama (`llama3`).

## Структура

- `docker-compose.yml` — поднимает Ollama в контейнере
- `requirements.txt` — зависимости (`pytest`, `requests`)
- `test/conftest.py` — фикстуры: `base_url`, `generate` (вызов `/api/generate`)
- `test/test_api.py` — тесты корректности API (валидные и ошибочные запросы)
- `test/test_hallucination.py` — тесты на галлюцинации (вопросы с известным ответом + отказ от выдумывания несуществующего закона)
- `test/test_consistency.py` — тест на согласованность повторных ответов

## Локальный запуск

1. Поднять Ollama в Docker и загрузить модель:

docker compose up -d
docker exec ollama-hm8 ollama pull llama3

2. Установить зависимости: pip install -r requirements.txt

3. Запустить все автотесты: pytest -v

## Проверка

`docker exec ollama-hm8 ollama list` — убедиться, что `llama3` скачана.
