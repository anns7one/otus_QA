"""Генерация API-автотестов моделью qwen2.5-coder, запущенной в Docker.

Что делает скрипт:
  1. читает спецификацию API и промпт из файлов;
  2. собирает из них один запрос;
  3. отправляет в Ollama внутри Docker-контейнера (порт 11435);
  4. достаёт код из ответа и сохраняет в tests/test_jsonplaceholder.py

Запуск:  python generate_tests.py
"""

import re
import sys
import urllib.error
import urllib.request
import json
from pathlib import Path

OLLAMA_URL = "http://localhost:11435/api/generate"
MODEL = "qwen2.5-coder:7b"

HERE = Path(__file__).resolve().parent
OUTPUT_FILE = HERE / "tests" / "test_jsonplaceholder.py"


def build_prompt() -> str:
    """Собирает запрос из спецификации и файла с промптом."""
    spec = (HERE / "api_spec.md").read_text(encoding="utf-8")
    prompt_template = (HERE / "prompt.md").read_text(encoding="utf-8")

    return f"""Ты senior AQA-инженер. Пишешь API-автотесты на Python 3 + pytest + requests.
Отвечаешь только кодом, без объяснений.

=== СПЕЦИФИКАЦИЯ API ===
{spec}

=== ЗАДАНИЕ ===
{prompt_template}

Верни готовый Python-файл с тремя тестами.
"""


def ask_model(prompt: str) -> str:
    """Отправляет запрос в Ollama и возвращает ответ модели."""
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,          # ждём ответ целиком, а не по кусочкам
        "options": {
            "temperature": 0.1,   # код, а не творчество: минимум случайности
            "num_predict": 2000,  # ограничение длины ответа
        },
    }).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))["response"]
    except urllib.error.URLError as error:
        print("Не удалось достучаться до Ollama в контейнере.")
        print(f"  Причина: {error}")
        print("  Проверьте, что контейнер запущен: docker ps")
        sys.exit(1)


def extract_code(answer: str) -> str:
    """Достаёт Python-код из ответа модели.
    """
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", answer, re.S)
    if blocks:
        # Если блоков несколько — берём самый длинный: это и есть файл с тестами
        return max(blocks, key=len).strip()
    return answer.strip()


def main() -> None:
    print(f"Модель: {MODEL} (в Docker-контейнере, порт 11435)")
    print("Отправляю запрос, это займёт 1-3 минуты ...")

    answer = ask_model(build_prompt())
    code = extract_code(answer)

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(code + "\n", encoding="utf-8")

    tests_found = re.findall(r"def (test_\w+)", code)
    print(f"\nСохранено: {OUTPUT_FILE.relative_to(HERE)}")
    print(f"Тестов в файле: {len(tests_found)}")
    for name in tests_found:
        print(f"  - {name}")
    print("\nЗапустите проверку:  pytest tests/ -v")


if __name__ == "__main__":
    main()
