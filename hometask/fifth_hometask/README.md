# Домашнее задание 5 — Тестирование безопасности промптов и защита LLM-агента

## Что делает

Учебный LLM-агент на FastAPI с намеренно уязвимой конфигурацией: слабый
системный промпт, неограниченный SQL-инструмент (SQLite: clients, orders,
secrets) и инструмент чтения внутренних документов. Цель — практически
исследовать классы атак на LLM-агентов (Prompt Injection, Tool Abuse,
RAG Poisoning, Encoding, Jailbreak) и затем построить защищённую версию.

## Требования

- Docker + Docker Compose
- Ollama, установленная локально, с моделью `qwen2.5:7b`
  (`ollama pull qwen2.5:7b`)
- Python 3.11+ (для автотестов на следующих этапах)

## Установка и запуск

1. Убедись, что Ollama запущена и модель скачана:
   ```powershell
   ollama pull qwen2.5:7b

2. Подними агента одной командой:
    ```docker compose up --build

3. Проверь, что агент отвечает: curl http://localhost:8100/health

Ожидается {"status":"ok","mode":"vulnerable"}.

4. Swagger UI для ручного тестирования: http://localhost:8100/docs

## Структура файлов

hometask/fifth_hometask/
├── README.md
├── docker-compose.yml
└── vulnerable/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py
    └── init_db.py
