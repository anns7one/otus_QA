"""Прогон промптов через Ollama и оценка результата LLM-судьёй по критериям CRITERIA."""

import json
import os

from openai import OpenAI

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11437/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")

CRITERIA = {
    "readability": "читаемость должна быть понятна структура и язык документа",
    "contextuality": (
        "контекстность — документ опирается именно на это требование, а не "
        "на общий шаблон, и не придумывает условий, которых нет в требовании"
    ),
    "goal_clarity": "чёткость целей должно быть понятно, что именно проверяется и зачем",
    "scenario_coverage": (
        "покрытие сценариев — учтены позитивные и негативные/граничные случаи "
        "(для test plan/QA report — полнота структуры документа)"
    ),
    "unambiguity": (
        "недвусмысленность — формулировки не допускают двух разных трактовок "
        "(например, расплывчатый ожидаемый результат без конкретики)"
    ),
    "atomicity": (
        "атомарность — каждый пункт документа (шаг, пункт чек-листа, строка "
        "таблицы) описывает одну проверяемую вещь, а не несколько сразу"
    ),
    "singularity": "единичность — нет пунктов, дублирующих друг друга по смыслу",
    "consistency": "непротиворечивость — пункты документа не противоречат друг другу",
    "correctness": (
        "корректность — значения и условия в документе (длины, маски, тексты "
        "ошибок) совпадают с требованием, без искажений и опечаток"
    ),
}

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def generate_document(prompt: str) -> str:
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


class JudgeParseError(RuntimeError):
    """Ответ судьи не удалось разобрать как JSON."""


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise JudgeParseError(f"В ответе судьи не найден JSON-блок. Ответ: {text!r}")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"Не удалось разобрать JSON судьи ({exc}). Ответ: {text!r}") from exc


MAX_JUDGE_ATTEMPTS = 2


def _judge(judge_prompt: str) -> dict:
    last_error = None
    for _ in range(MAX_JUDGE_ATTEMPTS):
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": judge_prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        try:
            return _extract_json(raw)
        except JudgeParseError as exc:
            last_error = exc
            # авторетрай: отдаём модели её же сломанный ответ и текст ошибки,
            # просим исправить — приём из методички (Тема 5, «Шлюз качества»)
            judge_prompt = (
                f"Твой предыдущий ответ не распарсился как JSON: {exc}\n\n"
                f"Твой предыдущий ответ был:\n{raw}\n\n"
                "Пришли ИСПРАВЛЕННУЮ версию — строго валидный JSON, без "
                "текста вокруг, со всеми ключами из схемы."
            )
    raise last_error


def score_document(artifact_type: str, requirement_text: str, generated_text: str) -> dict:
    criteria_lines = "\n".join(f'- {key}: {desc}' for key, desc in CRITERIA.items())
    schema = ", ".join(f'"{key}": {{"score": 0-5, "reason": "..."}}' for key in CRITERIA)
    judge_prompt = (
        f"Ты — независимый QA-эксперт, оцениваешь сгенерированный документ "
        f"типа «{artifact_type}» по исходному требованию.\n\n"
        f"Требование:\n{requirement_text}\n\n"
        f"Сгенерированный документ:\n{generated_text}\n\n"
        f"Оцени по шкале 0-5 каждый критерий:\n{criteria_lines}\n\n"
        f"Ответь строго одним JSON без текста вокруг: {{{schema}}}\n"
        "В текстах reason НЕ используй двойные кавычки для выделения терминов "
        "— используй одинарные кавычки или обходись без них, иначе JSON "
        "сломается на этих кавычках."
    )
    return _judge(judge_prompt)


def evaluate_prompt(artifact_type: str, prompt: str, requirement_text: str) -> dict:
    generated_text = generate_document(prompt)
    try:
        scores = score_document(artifact_type, requirement_text, generated_text)
    except JudgeParseError as exc:
        scores = {"error": str(exc)}
    return {"artifact_type": artifact_type, "generated_text": generated_text, "scores": scores}
