import json
import shutil
import subprocess
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:11400"
MODEL = "qwen2.5:7b"
MAX_TOKENS = 1500
PROJECT_DIR = Path(__file__).parent


def start_ollama():
    compose_files = ["-f", "docker-compose.yml"]
    if shutil.which("nvidia-smi"):
        compose_files += ["-f", "docker-compose.gpu.yml"]
    subprocess.run(
        ["docker", "compose", *compose_files, "up", "-d"],
        cwd=PROJECT_DIR,
        check=True,
    )


def wait_ready(timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/api/version", timeout=2)
            if response.ok:
                return response.json()["version"]
        except requests.RequestException:
            pass
        time.sleep(1)
    raise TimeoutError(f"Ollama не ответила за {timeout} с")


def ensure_model(model=MODEL):
    response = requests.get(f"{BASE_URL}/api/tags", timeout=10)
    response.raise_for_status()
    if any(item["name"] == model for item in response.json()["models"]):
        print(f"Модель {model} уже скачана")
        return

    print(f"Скачиваю модель {model}...")
    with requests.post(
        f"{BASE_URL}/api/pull",
        json={"model": model},
        stream=True,
        timeout=(10, 300),
    ) as pull:
        pull.raise_for_status()
        last_status = None
        for line in pull.iter_lines():
            event = json.loads(line)
            if "error" in event:
                raise RuntimeError(event["error"])
            if event.get("status") != last_status:
                last_status = event.get("status")
                print(last_status)


def chat(prompt, schema=None, temperature=0.2, seed=42):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "seed": seed, "num_predict": MAX_TOKENS},
    }
    if schema:
        payload["format"] = schema

    response = requests.post(f"{BASE_URL}/api/chat", json=payload, timeout=600)
    response.raise_for_status()
    content = response.json()["message"]["content"]
    return json.loads(content) if schema else content


def prepare_ollama():
    start_ollama()
    version = wait_ready()
    print(f"Ollama готова, версия {version}")
    ensure_model()


if __name__ == "__main__":
    prepare_ollama()
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "integer"}},
        "required": ["answer"],
    }
    result = chat("Сколько будет 2 + 2?", schema=schema, temperature=0)
    print(result)
    assert result["answer"] == 4
    print("Проверка пройдена")
