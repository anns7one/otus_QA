"""RAG-генератор ответов по базе знаний о теории тестирования.

Что делает скрипт:
  1. загружает базу знаний из dataset/knowledge_base.json;
  2. для вопроса пользователя ищет релевантные документы через семантические
     эмбеддинги (косинусная близость);
  3. передаёт найденные документы как контекст модели для генерации ответа.

Запуск:  python rag_generator.py
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
import math

OLLAMA_EMBED_URL = "http://localhost:11436/api/embeddings"
OLLAMA_GENERATE_URL = "http://localhost:11436/api/generate"
EMBED_MODEL = "nomic-embed-text"
GENERATE_MODEL = "llama3.2"
TOP_K = 4

HERE = Path(__file__).resolve().parent
DATASET_FILE = HERE / "dataset" / "knowledge_base.json"


def load_dataset() -> list[dict]:
    """Загружает базу знаний; если файла нет — понятная подсказка и выход."""
    if not DATASET_FILE.exists():
        print(f"Файл {DATASET_FILE.relative_to(HERE)} не найден.")
        print("Сначала запустите: python generate_dataset.py")
        sys.exit(1)
    return json.loads(DATASET_FILE.read_text(encoding="utf-8"))


def get_embedding(text: str) -> list[float]:
    """Получает эмбеддинг текста через Ollama (модель nomic-embed-text)."""
    payload = json.dumps({
        "model": EMBED_MODEL,
        "prompt": text,
    }).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))["embedding"]
    except urllib.error.URLError as error:
        print("Не удалось получить эмбеддинг от Ollama.")
        print(f"  Причина: {error}")
        print("  Проверьте, что контейнер запущен: docker ps")
        sys.exit(1)


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Косинусная близость двух векторов: 1.0 — одинаковое направление, 0 — независимость, -1.0 — противоположное."""
    dot_product = sum(a * b for a, b in zip(v1, v2))
    magnitude_v1 = math.sqrt(sum(a * a for a in v1))
    magnitude_v2 = math.sqrt(sum(b * b for b in v2))
    return dot_product / (magnitude_v1 * magnitude_v2)

def retrieve_relevant(question: str, docs_with_embeddings: list[tuple[dict, list[float]]], top_k: int = TOP_K) -> list[dict]:
    """Возвращает top_k документов, наиболее близких по смыслу к вопросу."""
    question_embedding = get_embedding(question)

    scored = [
        (cosine_similarity(question_embedding, doc_embedding), doc)
        for doc, doc_embedding in docs_with_embeddings
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [doc for score, doc in scored[:top_k]]

def generate_answer(question:str, context_docs:list[dict]) -> str:
    blocks = []
    for doc in context_docs:
        blocks.append(f"Title: {doc['title']}\nText: {doc['text']}\n")
    context = "\n".join(blocks)

    prompt = (
        f"Ты - ассистент, который отвечает на вопросы только на основе представленного контекста ниже.Если ответа нет в контексе, то "
        f"честно скажи, что информации недостаточно для ответа. Не выдумывай факты.Отвечай ТОЛЬКО на русском языке, не используй английские слова \n\n"
        f"Контекст:\n{context}\n\n"
        f"Вопрос: {question}\n\n"
        f"Дай развернутый ответ на русском языке, используя только информацию из контекста, объемом около 500 символов."
    )

    body = {
        "model": GENERATE_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 400,
        }
    }
    payload = json.dumps(body).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_GENERATE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))["response"].strip()
    except urllib.error.URLError as error:
        print("Не удалось получить ответ от Ollama.")
        print(f"  Причина: {error}")
        print("  Проверьте, что контейнер запущен: docker ps")
        sys.exit(1)

def main() -> None:
    dataset = load_dataset()
    print(f"Загружено документов: {len(dataset)}. Считаю эмбеддинги...")
    docs_with_embeddings = [(doc, get_embedding(doc["title"] + ". " + doc["text"])) for doc in dataset]
    print("Готово. Задавайте вопросы (пустая строка или exit — выход).\n")

    while True:
        question = input("Вопрос: ").strip()
        if not question or question.lower() in ("exit", "quit", "выход"):
            print("До встречи!")
            break

        relevant_docs = retrieve_relevant(question, docs_with_embeddings)
        print("Найденные документы:")
        for doc in relevant_docs:
            print(f"  - {doc['title']}")

        print("Генерирую ответ, это может занять несколько минут...")
        answer = generate_answer(question, relevant_docs)
        print(f"\nОтвет:\n{answer}\n")

        again = input("Задать ещё один вопрос? (да/нет, Enter = да): ").strip().lower()
        if again in ("нет", "no", "n", "exit", "quit", "выход"):
            print("До встречи!")
            break

if __name__ == "__main__":
    main()

