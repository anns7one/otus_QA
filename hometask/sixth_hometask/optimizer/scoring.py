"""Шаг 6: приоритеты тестов и покрытие требований.
Шаг 7: оценка читаемости эвристиками (LLM-рубрика — в llm.py, подключается сверху).

Сопоставление тест -> требование детерминированное: совпадают метод, путь,
статус И набор параметров. Требование без params matches только запрос без
параметров — иначе GET /posts (весь список) и GET /posts?userId=1
(отфильтрованный) слились бы в одно требование, хотя это разные проверки.
"""
import ast
import re
from dataclasses import dataclass

from .parse import Test

PRIORITY_WEIGHT = {"High": 3, "Medium": 2, "Low": 1}

_COMMON_STATUS_CODES = {200, 201, 204, 400, 401, 403, 404, 500}


def _weight(priority: str) -> int:
    """PRIORITY_WEIGHT[priority], но с понятной ошибкой вместо KeyError —
    requirements.json может прийти от пользователя (--requirements) с
    опечаткой или незнакомым значением приоритета."""
    try:
        return PRIORITY_WEIGHT[priority]
    except KeyError:
        raise ValueError(
            f"Неизвестный приоритет {priority!r} в requirements — "
            f"допустимые значения: {sorted(PRIORITY_WEIGHT)}"
        ) from None


def matches_requirement(test: Test, req: dict) -> bool:
    sig = test.signature
    if sig.method != req.get("method") or sig.path != req.get("path") or sig.status != req.get("status"):
        return False
    return sig.params == frozenset(req.get("params", []))


def map_requirements(test: Test, requirements: list[dict]) -> list[dict]:
    return [r for r in requirements if matches_requirement(test, r)]


def priority_for(test: Test, requirements: list[dict]) -> str | None:
    matched = map_requirements(test, requirements)
    if not matched:
        return None
    return max(matched, key=lambda r: _weight(r["priority"]))["priority"]


@dataclass
class Coverage:
    covered_ids: set
    uncovered_ids: set
    total: int
    percent: float
    weighted_percent: float


def compute_coverage(tests: list[Test], requirements: list[dict]) -> Coverage:
    covered = set()
    for t in tests:
        for r in map_requirements(t, requirements):
            covered.add(r["id"])
    all_ids = {r["id"] for r in requirements}
    uncovered = all_ids - covered

    total_weight = sum(_weight(r["priority"]) for r in requirements)
    covered_weight = sum(_weight(r["priority"]) for r in requirements if r["id"] in covered)

    return Coverage(
        covered_ids=covered,
        uncovered_ids=uncovered,
        total=len(requirements),
        percent=round(100 * len(covered) / len(requirements), 1) if requirements else 0.0,
        weighted_percent=round(100 * covered_weight / total_weight, 1) if total_weight else 0.0,
    )


# ---- Шаг 7: читаемость (эвристическая часть, без LLM) ----

def _looks_like_placeholder_name(name: str) -> bool:
    return bool(re.fullmatch(r"test_\d+", name)) or len(name) <= 10


def _count_magic_numbers(node: ast.FunctionDef) -> int:
    count = 0
    for child in ast.walk(node):
        if (isinstance(child, ast.Constant) and isinstance(child.value, int)
                and not isinstance(child.value, bool)
                and child.value not in _COMMON_STATUS_CODES
                and child.value not in (0, 1)):
            count += 1
    return count


def heuristic_readability(test: Test) -> float:
    """0-100, пять признаков по 20 баллов — прозрачно и объяснимо в отчёте."""
    score = 0.0
    if not _looks_like_placeholder_name(test.name):
        score += 20
    if test.docstring:
        score += 20
    if test.loc <= 25:
        score += 20
    n_asserts = sum(1 for s in test.steps if s.kind == "assert")
    if 1 <= n_asserts <= 6:
        score += 20
    if _count_magic_numbers(test.node) <= 2:
        score += 20
    return score


def quality_score(test: Test, requirements: list[dict], readability: float) -> float:
    """quality = 0.6*readability + 0.4*покрытие (100, если хоть одно требование покрыто, иначе 0)."""
    coverage_bonus = 100.0 if map_requirements(test, requirements) else 0.0
    return round(0.6 * readability + 0.4 * coverage_bonus, 1)
