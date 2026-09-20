# Домашнее задание 5 — Тестирование безопасности промптов и защита LLM-агента

## Что делает

Учебный LLM-агент на FastAPI в двух версиях: `vulnerable/` (намеренно слабый
системный промпт, неограниченный SQL-инструмент и инструмент чтения
внутренних документов) и `secured/` (та же функциональность с Prompt
Isolation, Least Privilege, Input Guard и Output Guard). Цель — практически
исследовать классы атак на LLM-агентов (Prompt Injection, Prompt Leakage,
Tool Abuse, RAG Poisoning, Encoding, Jailbreak), задокументировать их,
построить защищённую версию и автоматизировать повторную проверку.

Подробный разбор — в [`REPORT.md`](REPORT.md).

## Требования

- Docker + Docker Compose
- Ollama, установленная локально, с моделью `qwen2.5:7b`
  (`ollama pull qwen2.5:7b`)
- Python 3.11+ и `pip install requests pytest` (для автотестов)

## Установка и запуск

1. Убедись, что Ollama запущена и модель скачана:
   ```powershell
   ollama pull qwen2.5:7b
   ```

2. Подними оба агента одной командой:
   ```powershell
   docker compose up --build
   ```

3. Проверь, что оба отвечают:
   ```powershell
   curl http://localhost:8100/health   # {"status":"ok","mode":"vulnerable"}
   curl http://localhost:8101/health   # {"status":"ok","mode":"secured"}
   ```

4. Swagger UI для ручного тестирования:
   - vulnerable: http://localhost:8100/docs
   - secured: http://localhost:8101/docs

## Автоматические тесты безопасности

```powershell
pip install requests pytest
pytest tests/ -v
```

19 payload'ов (6 классов атак + benign-контроль) против `secured`. Отчёт
pass/fail — [`tests/security_test_report.md`](tests/security_test_report.md).

## Структура файлов

```
hometask/fifth_hometask/
├── README.md
├── REPORT.md                    — полный отчёт (архитектура, атаки, защита, лимиты)
├── docker-compose.yml           — сервисы vulnerable (8100) и secured (8101)
├── evil_docs/                   — отравленные/легитимные документы для RAG-тестов
├── vulnerable/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── init_db.py
│   └── output_attack.md         — red-team лог против vulnerable (6 атак)
├── secured/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── init_db.py
│   └── secured_output.md        — red-team лог против secured (те же 6 атак)
└── tests/
    ├── payloads.json            — 19 payload'ов для автотестов
    ├── security_test.py
    ├── conftest.py
    └── security_test_report.md — сгенерированный отчёт pass/fail
```
