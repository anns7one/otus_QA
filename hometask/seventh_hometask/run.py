"""Прогоняет все 4 типа документов через Ollama.

Пишет:
- results/latest/<artifact_type>_results.md на каждый тип документа отдельно
  (test_case_results.md, checklist_results.md, test_plan_results.md,
  qa_report_results.md) — имя файла сразу говорит, что внутри, и это
  последний прогон. Это и есть "результаты тестирования" для сдачи.
- results/history/ — архив каждого прогона целиком (все 4 типа в одном
  файле на прогон, markdown + JSON с баллами), чтобы analyze_runs.py мог
  посчитать разброс оценок между прогонами (self-consistency check).
"""
import json
import re
import sys
from pathlib import Path

from prompt_generator import generate_all_prompts, load_requirement
from evaluator import evaluate_prompt, CRITERIA

RESULTS_DIR = Path("results")
LATEST_DIR = RESULTS_DIR / "latest"
HISTORY_DIR = RESULTS_DIR / "history"
_RUN_FOLDER_RE = re.compile(r"^(\d+)-progon$")


def next_run_number() -> int:
    numbers = []
    for p in HISTORY_DIR.glob("*-progon"):
        m = _RUN_FOLDER_RE.match(p.name)
        if m:
            numbers.append(int(m.group(1)))
    return max(numbers, default=0) + 1


def render_one(artifact_type: str, prompt: str, result: dict) -> str:
    lines = [f"# Результат: {artifact_type}", ""]
    lines.append("## Промпт")
    lines.append("```")
    lines.append(prompt)
    lines.append("```")
    lines.append("")
    lines.append("## Сгенерированный документ")
    lines.append("```")
    lines.append(result["generated_text"])
    lines.append("```")
    lines.append("")
    lines.append("## Оценка")
    scores = result["scores"]
    if "error" in scores:
        lines.append(f"**Ошибка оценки:** {scores['error']}")
    else:
        lines.append("| Критерий | Балл | Комментарий |")
        lines.append("|---|---|---|")
        for key in CRITERIA:
            entry = scores.get(key, {})
            lines.append(f"| {key} | {entry.get('score', '-')} | {entry.get('reason', '-')} |")
    lines.append("")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    requirement_path = "input/requirement.md"
    req = load_requirement(requirement_path)
    prompts = generate_all_prompts(requirement_path)

    results = {}
    for artifact_type, prompt in prompts.items():
        print(f"Генерирую и оцениваю: {artifact_type}...")
        results[artifact_type] = evaluate_prompt(artifact_type, prompt, req)

    for artifact_type, result in results.items():
        (LATEST_DIR / f"{artifact_type}_results.md").write_text(
            render_one(artifact_type, prompts[artifact_type], result), encoding="utf-8"
        )

    run_number = next_run_number()
    run_dir = HISTORY_DIR / f"{run_number:02d}-progon"
    run_dir.mkdir(parents=True, exist_ok=True)

    for artifact_type, result in results.items():
        (run_dir / f"{artifact_type}_results.md").write_text(
            render_one(artifact_type, prompts[artifact_type], result), encoding="utf-8"
        )
    scores_only = {artifact_type: result["scores"] for artifact_type, result in results.items()}
    (run_dir / "scores.json").write_text(
        json.dumps(scores_only, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Готово: " + ", ".join(f"results/latest/{t}_results.md" for t in results))
    print(f"В архив: results/history/{run_number:02d}-progon/")


if __name__ == "__main__":
    main()
