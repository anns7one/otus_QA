"""Шаг 4: поиск дублирующих шагов между разными тестами.

Правило фильтрации шума: одиночная проверка кода ответа (assert x.status_code
== N) встречается почти в каждом тесте и сама по себе не является находкой —
её игнорируем. Всё остальное совпадающее между >=2 тестами репортим: это либо
реально повторяющаяся логика (вынести в helper), либо повод присмотреться.
"""
import re
from collections import defaultdict

from .parse import Test

_TRIVIAL_STATUS_ONLY = re.compile(r"^ASSERT VAR\.status_code == \d+$")


def find_duplicate_steps(tests: list[Test]) -> list[dict]:
    groups: dict[str, list[str]] = defaultdict(list)
    for test in tests:
        seen_in_this_test = set()
        for step in test.steps:
            if step.normalized in seen_in_this_test:
                continue  # не дублировать в отчёте тест, у которого шаг повторён внутри себя
            seen_in_this_test.add(step.normalized)
            groups[step.normalized].append(test.name)

    result = []
    for normalized, names in groups.items():
        if len(names) < 2:
            continue
        if _TRIVIAL_STATUS_ONLY.match(normalized):
            continue
        result.append({"step": normalized, "tests": sorted(names)})

    result.sort(key=lambda g: (-len(g["tests"]), g["step"]))
    return result
