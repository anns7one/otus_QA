"""Шаг 9: проверка самого оптимизатора на посеянном наборе с известным ответом
(`ground_truth.json`). Это и есть «обучение» из ТЗ без fine-tuning модели —
калибровка порогов и правил на размеченных данных, а не подгонка весов сети.

Без Ollama: используем embedder (легковесная детерминированная модель,
temperature не применяется к эмбеддингам) и не трогаем Judge — LLM-часть
завязана на внешний сервис, который может быть недоступен у преподавателя.
"""
import ast
import json
from pathlib import Path

import pytest

from optimizer.duplicates import find_duplicate_steps
from optimizer.parse import Signature, Test, load_tests
from optimizer.scoring import compute_coverage, map_requirements, priority_for
from optimizer.similarity import find_duplicate_tests

ROOT = Path(__file__).parent.parent
SUITE_DIR = ROOT / "suites" / "jsonplaceholder"


@pytest.fixture(scope="module")
def tests():
    return load_tests(str(SUITE_DIR))


@pytest.fixture(scope="module")
def requirements():
    return json.loads((ROOT / "api_requirements.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ground_truth():
    return json.loads((ROOT / "ground_truth.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def embedder():
    # module-scope: модель грузится с диска один раз на весь файл, а не по
    # разу на каждый тест, который в ней нуждается.
    from optimizer.embeddings import Embedder
    return Embedder()


def test_coverage_matches_ground_truth(tests, requirements, ground_truth):
    coverage = compute_coverage(tests, requirements)
    expected = ground_truth["coverage"]
    assert coverage.total == expected["total"]
    assert len(coverage.covered_ids) == expected["covered"]
    assert sorted(coverage.uncovered_ids) == sorted(expected["uncovered"])
    assert coverage.weighted_percent == pytest.approx(expected["weighted_percent"], abs=0.1)


def test_priority_assignment(tests, requirements):
    by_name = {t.name: t for t in tests}
    assert priority_for(by_name["test_get_posts_list_returns_100_items"], requirements) == "High"
    assert priority_for(by_name["test_get_nonexistent_post_returns_404"], requirements) == "Medium"
    assert priority_for(by_name["test_delete"], requirements) == "Medium"
    assert priority_for(by_name["test_1"], requirements) is None


def test_requirement_mapping_respects_params(tests, requirements):
    """GET /posts без параметров и GET /posts?userId=1 — разные требования,
    не должны схлопнуться в одно (это и была ошибка из демо-ноутбука)."""
    by_name = {t.name: t for t in tests}
    unfiltered = {r["id"] for r in map_requirements(by_name["test_get_posts_list_returns_100_items"], requirements)}
    filtered = {r["id"] for r in map_requirements(by_name["test_get_posts_filtered_by_user_id"], requirements)}
    assert unfiltered == {"REQ-01"}
    assert filtered == {"REQ-04"}


def test_duplicate_steps_found(tests, ground_truth):
    found = {g["step"]: set(g["tests"]) for g in find_duplicate_steps(tests)}
    for expected in ground_truth["duplicate_steps_must_find"]:
        matching = [tests_set for _, tests_set in found.items() if tests_set >= set(expected["tests"])]
        assert matching, f"не найден ожидаемый дубль шага: {expected['description']}"


def test_trivial_status_check_not_reported(tests):
    """Одиночная проверка status_code не должна попадать в отчёт — иначе шум
    забивает реальные находки (см. ground_truth.duplicate_steps_must_not_find)."""
    groups = find_duplicate_steps(tests)
    assert not any(g["step"].endswith("VAR.status_code == 200") for g in groups)


def test_duplicate_tests_structural_only(tests, ground_truth):
    """Без эмбеддингов (быстрый путь) находятся только тесты с полностью
    совпадающим набором шагов — структурно точные дубли."""
    pairs = find_duplicate_tests(tests)
    found_pairs = {frozenset((p.a, p.b)) for p in pairs}
    exact_expected = [d for d in ground_truth["duplicate_tests"] if d["type"] == "exact"]
    for expected in exact_expected:
        assert frozenset(expected["tests"]) in found_pairs


def test_duplicate_tests_with_embeddings_finds_near_dup(tests, ground_truth, embedder):
    """С эмбеддингами находится и семантический (не структурный) дубль —
    пара, которую чистый Jaccard не поймал бы (0.25, ниже порога)."""
    pairs = find_duplicate_tests(tests, embedder=embedder)
    found_pairs = {frozenset((p.a, p.b)) for p in pairs}
    for expected in ground_truth["duplicate_tests"]:
        assert frozenset(expected["tests"]) in found_pairs, f"не найдена пара {expected['tests']}"


def test_duplicate_tests_no_false_positives(tests, ground_truth, embedder):
    """Ложные близнецы (разные требования/методы) не должны попадать в отчёт
    ни с эмбеддингами, ни без — сигнатурный барьер должен их отсечь."""
    pairs = find_duplicate_tests(tests, embedder=embedder)
    found_pairs = {frozenset((p.a, p.b)) for p in pairs}
    for a, b in ground_truth["not_duplicates"]:
        assert frozenset((a, b)) not in found_pairs, f"ложное срабатывание на паре {a} / {b}"


def _unsigned_test(name: str) -> Test:
    """Тест, у которого парсер не смог найти requests.*-вызов (например, он
    делегирует в helper-функцию) — сигнатура и шаги пустые."""
    dummy_node = ast.parse("def dummy(): pass").body[0]
    return Test(
        name=name, file="synthetic.py", lineno=1, loc=1, docstring=None,
        signature=Signature(None, None, None, frozenset()), steps=[], node=dummy_node,
    )


def test_unsigned_tests_are_not_false_duplicates():
    """Регрессия: два теста без распознанной сигнатуры не должны считаться
    100% дублями друг друга только потому, что про них обоих ничего не
    известно (пустой step-set, Jaccard(пусто, пусто) == 1.0)."""
    pairs = find_duplicate_tests([_unsigned_test("test_alpha"), _unsigned_test("test_beta")])
    assert pairs == []
