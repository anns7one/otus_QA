"""CLI: python -m optimizer --tests <dir> --requirements <file> [--no-llm] [--out report.md]

--no-llm убирает эмбеддинги и LLM-судью: остаются только детерминированные
проверки (парсер, точные дубли шагов, дубли тестов с Jaccard==1.0, приоритеты,
эвристическая читаемость). Без него нужна Ollama с моделью из LLM_MODEL.
"""
import argparse
import json
import sys
from pathlib import Path

from .duplicates import find_duplicate_steps
from .llm import LLMUnavailable
from .parse import load_tests
from .report import render_report
from .scoring import compute_coverage, heuristic_readability, map_requirements, priority_for, quality_score
from .similarity import find_duplicate_tests


def combine_readability(heuristic: float, llm_score) -> float:
    """Половина — прозрачные эвристики, половина — LLM-рубрика (если есть).
    Без LLM (--no-llm) остаётся только эвристическая часть."""
    if llm_score is None:
        return heuristic
    return round(0.5 * heuristic + 0.5 * (llm_score * 20), 1)


def run(tests_dir: str, requirements_path: str, use_llm: bool) -> str:
    requirements = json.loads(Path(requirements_path).read_text(encoding="utf-8"))
    tests = load_tests(tests_dir)

    embedder = judge = None
    if use_llm:
        from .embeddings import Embedder
        from .llm import Judge
        embedder = Embedder()
        judge = Judge()

    duplicate_steps = find_duplicate_steps(tests)
    duplicate_tests = find_duplicate_tests(tests, embedder=embedder, judge=judge)
    coverage = compute_coverage(tests, requirements)

    items = []
    for t in tests:
        matched = map_requirements(t, requirements)
        heuristic = heuristic_readability(t)
        llm_score = None
        if judge is not None:
            req_text = matched[0]["text"] if matched else None
            try:
                llm_score = judge.rate_readability(t, req_text).score
            except LLMUnavailable as exc:
                print(f"Внимание: {exc} — дальше читаемость только по эвристикам.", file=sys.stderr)
                judge = None
        readability = combine_readability(heuristic, llm_score)
        quality = quality_score(t, requirements, readability)
        items.append({
            "name": t.name,
            "priority": priority_for(t, requirements),
            "requirements": [r["id"] for r in matched],
            "quality": quality,
        })

    return render_report(items, duplicate_steps, duplicate_tests, coverage, requirements)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Оптимизатор автотестов: дубли, приоритеты, качество")
    parser.add_argument("--tests", required=True, help="папка с pytest-файлами (sample_*.py)")
    parser.add_argument("--requirements", default="api_requirements.json")
    parser.add_argument("--no-llm", action="store_true", help="без эмбеддингов и LLM-судьи")
    parser.add_argument("--out", default=None, help="путь для сохранения отчёта; без него печать в stdout")
    args = parser.parse_args(argv)

    report = run(args.tests, args.requirements, use_llm=not args.no_llm)

    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"Отчёт сохранён в {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
