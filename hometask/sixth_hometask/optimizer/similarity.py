"""Шаг 5: поиск дублирующих/похожих тестов.

Воронка: сигнатурный барьер -> структурное совпадение шагов -> эмбеддинги ->
LLM-судья для спорной зоны. Барьер по (метод, путь, статус, параметры)
отсекает разные по смыслу тесты ещё до всякой похожести текста — это лечит
ошибку из демо-ноутбука преподавателя, где success-логин и wrong-password
получили cosine 0.894 (выше настоящего дубля 0.664).
"""
import sys
from collections import defaultdict
from dataclasses import dataclass

from .llm import LLMUnavailable
from .parse import Test

EXACT_JACCARD = 1.0
NEAR_JACCARD_NO_EMBED = 0.55     # запасной порог, если эмбеддингов нет (--no-llm)
EMBED_HIGH = 0.80                # выше -> считаем похожим без судьи
EMBED_LOW = 0.55                 # ниже -> не похож, судья не вызывается


@dataclass
class DuplicatePair:
    a: str
    b: str
    kind: str            # "exact" | "near" | "llm"
    score: float
    reason: str = ""


def _step_set(test: Test) -> frozenset:
    return frozenset(s.normalized for s in test.steps)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


def bucket_by_signature(tests: list[Test]) -> dict:
    """Барьер: тесты группируются только если у них совпадают метод, путь,
    статус И параметры. Разные исходы (200 против 404) или разные параметры
    (весь список против отфильтрованного) никогда не попадут в одну группу —
    сравнивать их дальше не нужно.

    Тесты, у которых парсер не нашёл ни одного requests.*-вызова (сигнатура
    method=None), не группируются вообще — иначе любые два таких теста (где
    угодно, по любой причине) получали бы пустой набор шагов, Jaccard между
    пустыми множествами равен 1.0, и они засчитывались бы как 100% дубль
    друг друга просто потому, что про них обоих ничего не удалось узнать."""
    buckets = defaultdict(list)
    for t in tests:
        if t.signature.method is None:
            continue
        buckets[t.signature.key()].append(t)
    return buckets


def text_for_embedding(test: Test) -> str:
    doc = test.docstring or ""
    steps = " ".join(s.normalized for s in test.steps)
    return f"{doc} {steps}"


def find_duplicate_tests(tests: list[Test], embedder=None, judge=None) -> list[DuplicatePair]:
    pairs = []
    for group in bucket_by_signature(tests).values():
        if len(group) < 2:
            continue

        # Эмбеддим тексты бакета один раз, а не по разу на каждую пару —
        # для бакета из k тестов иначе было бы O(k^2) обращений к модели
        # вместо O(k).
        sim_matrix = None
        if embedder is not None:
            texts = [text_for_embedding(t) for t in group]
            sim_matrix = embedder.pairwise_similarity(texts)

        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                jac = jaccard(_step_set(a), _step_set(b))

                if jac >= EXACT_JACCARD:
                    pairs.append(DuplicatePair(a.name, b.name, "exact", jac, "identical step set"))
                    continue

                if sim_matrix is not None:
                    score = float(sim_matrix[i][j])
                    if score >= EMBED_HIGH:
                        pairs.append(DuplicatePair(a.name, b.name, "near", score, f"embedding cosine={score:.3f}"))
                    elif score >= EMBED_LOW and judge is not None:
                        try:
                            verdict = judge.is_duplicate(a, b)
                        except LLMUnavailable as exc:
                            print(f"Внимание: {exc} — LLM-судья для похожих тестов выключен до конца прогона.", file=sys.stderr)
                            judge = None
                            continue
                        if verdict.duplicate:
                            pairs.append(DuplicatePair(a.name, b.name, "llm", score, verdict.reason))
                elif jac >= NEAR_JACCARD_NO_EMBED:
                    pairs.append(DuplicatePair(a.name, b.name, "near", jac, f"step overlap jaccard={jac:.2f} (no embedder)"))

    pairs.sort(key=lambda p: (-p.score, p.a, p.b))
    return pairs
