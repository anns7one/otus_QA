"""Оценка качества самого требования (не сгенерированного документа) по
характеристикам хорошего требования (EPAM, «Тестирование ПО. Базовый курс»,
разд. 2.2).

ponytail: из исходного списка EPAM выброшены 2 характеристики —
«проранжированность по важности/стабильности/срочности» (бессмысленна без
явных меток приоритета в requirement.md — их там нет, добавить вместе с
критерием, если в requirement.md появятся приоритеты) и «последовательность»
(граница термина не восстановилась при копировании текста — см.
knowledge/summaries/epam-bazovyi-kurs-kachestvo-trebovaniy.md в вики-базе).
"""
import sys
from pathlib import Path

from evaluator import _judge, JudgeParseError
from prompt_generator import load_requirement

REQUIREMENT_CRITERIA = {
    "completeness": "завершённость — описаны все поля, их правила валидации и поведение системы, нет недосказанностей",
    "atomicity": "атомарность — каждый пункт требования описывает одну проверяемую вещь, а не несколько сразу",
    "singularity": "единичность — нет пунктов, дублирующих друг друга по смыслу",
    "consistency": "непротиворечивость — правила не противоречат друг другу",
    "feasibility": "выполнимость — описанные правила технически реализуемы как есть",
    "necessity": "нужность — в тексте нет условий, не относящихся к задаче, которую решает это требование",
    "currency": "актуальность — требование не содержит явно устаревших или гипотетических условий",
    "traceability": "прослеживаемость — к каждому полю или кнопке можно привязать конкретное правило или поведение",
    "modifiability": "модифицируемость — пункты независимы настолько, что один можно изменить, не трогая остальные",
    "correctness": "корректность — правила внутренне согласованы и не содержат явных ошибок/опечаток в логике",
    "verifiability": "проверяемость — по каждому пункту можно сформулировать хотя бы один тест-кейс",
}


def build_requirement_judge_prompt(requirement_text: str) -> str:
    criteria_lines = "\n".join(f"- {key}: {desc}" for key, desc in REQUIREMENT_CRITERIA.items())
    schema = ", ".join(f'"{key}": {{"score": 0-5, "reason": "..."}}' for key in REQUIREMENT_CRITERIA)
    return (
        "Ты — эксперт по анализу требований (requirements engineer). Оцени "
        "КАЧЕСТВО САМОГО ТЕКСТА ТРЕБОВАНИЯ ниже (не документа, который по "
        "нему можно сгенерировать).\n\n"
        f"Требование:\n{requirement_text}\n\n"
        f"Оцени по шкале 0-5 каждую характеристику:\n{criteria_lines}\n\n"
        f"Ответь строго одним JSON без текста вокруг: {{{schema}}}\n"
        "В текстах reason НЕ используй двойные кавычки для выделения терминов "
        "— используй одинарные кавычки или обходись без них, иначе JSON "
        "сломается на этих кавычках."
    )


def score_requirement(requirement_text: str) -> dict:
    return _judge(build_requirement_judge_prompt(requirement_text))


def render(requirement_text: str, scores: dict) -> str:
    lines = ["# Оценка качества требования", "", "## Требование", "```", requirement_text, "```", ""]
    lines.append("## Оценка")
    if "error" in scores:
        lines.append(f"**Ошибка оценки:** {scores['error']}")
    else:
        lines.append("| Характеристика | Балл | Комментарий |")
        lines.append("|---|---|---|")
        for key in REQUIREMENT_CRITERIA:
            entry = scores.get(key, {})
            lines.append(f"| {key} | {entry.get('score', '-')} | {entry.get('reason', '-')} |")
    lines.append("")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    requirement_text = load_requirement("requirement.md")
    try:
        scores = score_requirement(requirement_text)
    except JudgeParseError as exc:
        scores = {"error": str(exc)}
    Path("requirement_quality_results.md").write_text(
        render(requirement_text, scores), encoding="utf-8"
    )
    print("Готово: requirement_quality_results.md")


if __name__ == "__main__":
    main()
