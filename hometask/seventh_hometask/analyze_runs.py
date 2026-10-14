"""Собирает баллы по всем сохранённым прогонам (results/history/scores_*.json)
и считает среднее/мин/макс по каждому критерию и типу документа. Это и есть
self-consistency check: если баллы между прогонами сильно "плавают" — значит,
одному прогону доверять нельзя, и это видно по разбросу мин/макс, а не
спрятано."""
import json
import sys
from collections import defaultdict
from pathlib import Path

HISTORY_DIR = Path("results") / "history"


def load_all_runs() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(HISTORY_DIR.glob("*-progon/scores.json"))]


def aggregate(runs: list[dict]) -> dict:
    buckets = defaultdict(list)
    for run in runs:
        for artifact_type, scores in run.items():
            for criterion, entry in scores.items():
                if criterion == "error":
                    continue
                score = entry.get("score")
                if isinstance(score, (int, float)):
                    buckets[(artifact_type, criterion)].append(score)
    return buckets


def render_table(buckets: dict, n_runs: int) -> str:
    lines = [f"# Стабильность оценок по {n_runs} прогонам", "",
             "| Тип документа | Критерий | Прогонов | Среднее | Мин | Макс |",
             "|---|---|---|---|---|---|"]
    for (artifact_type, criterion), scores in sorted(buckets.items()):
        avg = sum(scores) / len(scores)
        lines.append(f"| {artifact_type} | {criterion} | {len(scores)} | {avg:.1f} | {min(scores)} | {max(scores)} |")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    runs = load_all_runs()
    if not runs:
        print("Нет сохранённых прогонов в results/history/ — сначала запусти run.py несколько раз.")
        return
    table = render_table(aggregate(runs), len(runs))
    print(table)
    Path("results/stability_report.md").write_text(table, encoding="utf-8")


if __name__ == "__main__":
    main()
