"""LLM-судья через Ollama (OpenAI-совместимый API, как в ДЗ 5).

Используется только там, где эвристики/не хватает структуры. Спорные пары
в шаге 5 (внутри одной корзины по сигнатуре, эмбеддинги в средней зоне) и
вторая половина читаемости в шаге 7 (насколько assert'ы реально покрывают
требование — этого heuristic_readability не видит, она смотрит только на
поверхностные признаки: имя, длину, docstring, число assert'ов).
Температура 0 — нужна повторяемость оценки, а не творчество.
"""
import ast
import json
import os
from dataclasses import dataclass

from openai import OpenAI

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")


class LLMUnavailable(RuntimeError):
    """Ollama/LLM-бэкенд недоступен или вернул ошибку на запросе."""


@dataclass
class DuplicateVerdict:
    duplicate: bool
    reason: str


@dataclass
class ReadabilityVerdict:
    score: int  # 0-5
    reason: str


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}


class Judge:
    def __init__(self, model: str = LLM_MODEL):
        self._client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        self._model = model

    def _ask(self, prompt: str) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
        except Exception as exc:
            raise LLMUnavailable(
                f"Ollama/{self._model} не отвечает ({exc}). Проверь, что Ollama запущена "
                "и модель скачана, либо запусти с --no-llm."
            ) from exc
        return _extract_json(response.choices[0].message.content or "")

    def is_duplicate(self, test_a, test_b) -> DuplicateVerdict:
        prompt = (
            "Ты — QA-инженер. Ниже два автотеста на Python. Определи, дублируют ли "
            "они друг друга (проверяют одно и то же поведение системы), или это разные "
            "проверки, даже если код похож. Ответь строго одним JSON без текста вокруг: "
            '{"duplicate": true или false, "reason": "коротко почему"}\n\n'
            f"--- Тест A: {test_a.name} ---\n{ast.unparse(test_a.node)}\n\n"
            f"--- Тест B: {test_b.name} ---\n{ast.unparse(test_b.node)}"
        )
        data = self._ask(prompt)
        return DuplicateVerdict(
            duplicate=bool(data.get("duplicate", False)),
            reason=str(data.get("reason") or "не удалось разобрать ответ модели"),
        )

    def rate_readability(self, test, requirement_text: str | None) -> ReadabilityVerdict:
        req_line = requirement_text or "не найдено связанное требование — это тоже недостаток"
        prompt = (
            "Ты — ревьюер автотестов. Оцени тест по шкале 0-5 по трём критериям: "
            "понятность имени и docstring, структура (подготовка -> действие -> проверка), "
            "и главное — насколько assert'ы теста реально проверяют то, что заявлено в "
            f"требовании. Требование этого теста: {req_line}\n\n"
            f"Код теста:\n{ast.unparse(test.node)}\n\n"
            'Ответь строго одним JSON без текста вокруг: {"score": 0-5, "reason": "коротко почему"}'
        )
        data = self._ask(prompt)
        try:
            score = int(data.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        return ReadabilityVerdict(
            score=max(0, min(5, score)),
            reason=str(data.get("reason") or "не удалось разобрать ответ модели"),
        )
