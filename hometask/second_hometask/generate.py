"""ДЗ-2: генерация тестовой документации доработанной моделью.

Запуск:
    python generate.py                    # авто: ollama если доступна, иначе n-gram
    python generate.py --backend ngram    # только обученная n-gram модель
    python generate.py --backend ollama   # локальная LLM через Ollama

Модель обучается при каждом запуске — статистика обучения печатается в консоль.

Разделение труда (принцип «код агрегирует, модель обобщает»):
числа для отчёта считает код из results.json, модель только формулирует текст.
Так в отчёте не может появиться выдуманная цифра.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from backends import NgramBackend, OllamaBackend
from corpus import TRAINING_CORPUS
from model import DocGeneratorLLM

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
REQUIREMENTS_FILE = BASE_DIR / "requirements" / "business-requirements.md"
RESULTS_FILE = BASE_DIR / "results.json"

DOCUMENTS = {
    "test-cases": "test-cases.md",
    "checklist": "checklist.md",
    "test-plan": "test-plan.md",
    "test-report": "test-report.md",
}


def train_model(order: int = 3) -> DocGeneratorLLM:
    """Обучение модели. Печатает, что именно она выучила."""
    model = DocGeneratorLLM(order=order)
    model.train(TRAINING_CORPUS)
    print(f"[1/3] Обучение модели (n-граммы порядка {order})")
    for key, value in model.stats().items():
        print(f"      {key}: {value}")
    example = model.predict_next_word(" ".join(TRAINING_CORPUS[0].split()[: order - 1]))
    print(f"      проверка предсказания: '{example}'")
    return model


def aggregate_results() -> dict:
    """Числа для отчёта считает КОД, а не модель."""
    data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    results = data["results"]
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "passed"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
    }
    defects = [r["defect"] for r in results if r.get("defect")]
    return {"meta": data, "summary": summary, "results": results, "defects": defects}


SEVERITY_ORDER = {"Blocker": 4, "Critical": 3, "Major": 2, "Minor": 1, "Trivial": 0}


def decide_verdict(agg: dict) -> tuple[str, str]:
    """Вердикт go/no-go выносит КОД по чётким порогам, а не модель.

    Модели свойствен optimism bias: она сглаживает вывод и может написать
    «релиз разрешён» при упавшем кейсе. Поэтому решение детерминированное,
    а модели остаётся только обосновать его словами.
    """
    s = agg["summary"]
    worst = max(
        (SEVERITY_ORDER.get(d.get("severity", "Minor"), 1) for d in agg["defects"]),
        default=-1,
    )
    if s["failed"] == 0:
        return "релиз разрешён", "все тест-кейсы пройдены, открытых дефектов нет"
    if worst >= 3:  # Critical / Blocker
        return (
            "релиз не рекомендуется",
            f"есть незакрытый дефект уровня Critical или выше ({s['failed']} кейс(ов) не пройдено)",
        )
    return (
        "релиз с оговорками",
        f"{s['failed']} кейс(ов) не пройдено, есть незакрытый дефект уровня Major",
    )


def facts_block(agg: dict) -> str:
    """Факты прогона для промпта — модель обязана использовать их как есть."""
    s = agg["summary"]
    meta = agg["meta"]
    lines = [
        "Факты прогона (НЕ ИЗМЕНЯЙ эти числа и идентификаторы):",
        f"  Прогон: {meta['run_id']}, окружение: {meta['environment']}",
        f"  Всего тест-кейсов: {s['total']}",
        f"  Пройдено: {s['passed']}",
        f"  Не пройдено: {s['failed']}",
        "",
        "  Результаты по кейсам:",
    ]
    for r in agg["results"]:
        mark = "PASSED" if r["status"] == "passed" else "FAILED"
        lines.append(f"    - {r['id']} ({r['requirement']}, {r['priority']}): {r['title']} — {mark}")
    if agg["defects"]:
        lines.append("")
        lines.append("  Дефекты:")
        for d in agg["defects"]:
            lines.append(f"    - {d['id']} [{d['severity']}] {d['summary']}")
            lines.append(f"      Фактически: {d['actual']}")
            lines.append(f"      Ожидалось: {d['expected']}")

    verdict, reason = decide_verdict(agg)
    lines += [
        "",
        f"  ВЕРДИКТ (решён по правилам, НЕ меняй его): {verdict}",
        f"  Основание: {reason}",
        "  В разделе «Вывод о релизе» повтори именно эту формулировку вердикта "
        "и обоснуй её словами.",
    ]
    return "\n".join(lines)


def render_report_facts(agg: dict) -> str:
    """Фактическая часть отчёта — рендерит КОД, а не модель.

    Сводка, таблица результатов, дефекты и покрытие целиком выводятся из
    results.json. Модель к этим цифрам не прикасается, поэтому исказить их
    не может в принципе.
    """
    s = agg["summary"]
    meta = agg["meta"]
    lines = [
        "# Отчёт о тестировании (Test Completion Report)",
        "",
        f"- Прогон: {meta['run_id']}",
        f"- Объект: {meta['page_url']}",
        f"- Окружение: {meta['environment']}",
        f"- Дата: {meta['executed_at']}",
        "",
        "## Сводка",
        "",
        "| Показатель | Значение |",
        "|---|---|",
        f"| Всего тест-кейсов | {s['total']} |",
        f"| Пройдено | {s['passed']} |",
        f"| Не пройдено | {s['failed']} |",
        "",
        "## Результаты по кейсам",
        "",
        "| ID | Требование | Приоритет | Заголовок | Статус |",
        "|---|---|---|---|---|",
    ]
    for r in agg["results"]:
        status = "PASSED" if r["status"] == "passed" else "FAILED"
        lines.append(
            f"| {r['id']} | {r['requirement']} | {r['priority']} | {r['title']} | {status} |"
        )

    lines += ["", "## Дефекты", ""]
    if agg["defects"]:
        for d in agg["defects"]:
            lines += [
                f"### {d['id']} — {d['summary']}",
                "",
                f"- Серьёзность: {d['severity']}",
                f"- Фактически: {d['actual']}",
                f"- Ожидалось: {d['expected']}",
                "",
            ]
    else:
        lines += ["Дефектов не обнаружено.", ""]

    lines += ["## Покрытие требований", "", "| Требование | Кейс | Статус |", "|---|---|---|"]
    for r in agg["results"]:
        status = "покрыто" if r["status"] == "passed" else "покрыто, дефект"
        lines.append(f"| {r['requirement']} | {r['id']} | {status} |")
    lines.append("")
    return "\n".join(lines)


RISK_HEADING = "## Оценка остаточного риска"
VERDICT_HEADING = "## Вывод о релизе"


def extract_narrative(model_output: str) -> str | None:
    """Достать из ответа модели только два интерпретирующих раздела.

    Малая модель часто игнорирует «напиши только два раздела» и заново
    пересказывает факты. Вместо того чтобы доверять её дисциплине, вырезаем
    нужное сами; если разделов нет — возвращаем None, и вызывающий код делает
    повторную попытку с конкретным фидбеком.
    """
    if RISK_HEADING not in model_output or VERDICT_HEADING not in model_output:
        return None
    narrative = model_output[model_output.index(RISK_HEADING) :]
    # отсечь всё, что модель дописала после вывода о релизе
    tail_start = narrative.index(VERDICT_HEADING) + len(VERDICT_HEADING)
    next_heading = narrative.find("\n# ", tail_start)
    if next_heading != -1:
        narrative = narrative[:next_heading]
    return narrative.strip()


def render_report_narrative(backend, facts: str, max_attempts: int = 2) -> str:
    """Генерация интерпретирующей части с ретраем при несоблюдении формата."""
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        raw = backend.render("test-report", facts + feedback)
        narrative = extract_narrative(raw)
        if narrative:
            return narrative
        print(f"      попытка {attempt}: модель не вернула требуемые разделы, повтор")
        feedback = (
            "\n\nПредыдущий ответ отклонён: не было разделов "
            f"«{RISK_HEADING}» и «{VERDICT_HEADING}». "
            "Верни ТОЛЬКО эти два раздела с такими заголовками. "
            "Не повторяй факты прогона и не пиши другие разделы."
        )
    return (
        f"{RISK_HEADING}\n\n_Модель не сформировала раздел за "
        f"{max_attempts} попытки — требуется ручное заполнение._\n\n"
        f"{VERDICT_HEADING}\n\n_Требуется ручное заполнение._"
    )


def verify_test_cases(text: str) -> list[str]:
    """Проверка тест-кейсов: ровно 3 штуки и хотя бы один негативный."""
    warnings = []
    ids = re.findall(r"\bTC-\d+\b", text)
    unique_ids = sorted(set(ids))
    if len(unique_ids) != 3:
        warnings.append(f"ожидалось 3 тест-кейса, найдено {len(unique_ids)}: {unique_ids}")
    if "негативный" not in text.lower():
        warnings.append("нет ни одного негативного кейса — задание требует один негативный")
    if text.lower().count("**шаги:**") != len(unique_ids):
        warnings.append("не у каждого кейса есть блок «Шаги»")
    return warnings


def verify_report_numbers(report_text: str, agg: dict) -> list[str]:
    """Шлюз качества для отчёта.

    Проверяет три разных класса проблем — схемная валидация ловит только первый,
    поэтому нужны все три:
      1. числа и ID совпадают с фактами прогона;
      2. модель не придумала лишние идентификаторы;
      3. текст не съехал в транслитерацию (типовой сбой малых моделей).
    """
    warnings = []
    s = agg["summary"]

    if str(s["passed"]) not in report_text:
        warnings.append(f"в отчёте не найдено число пройденных тестов ({s['passed']})")
    if str(s["failed"]) not in report_text:
        warnings.append(f"в отчёте не найдено число упавших тестов ({s['failed']})")
    for r in agg["results"]:
        if r["id"] not in report_text:
            warnings.append(f"в отчёте не упомянут {r['id']}")

    known_ids = {r["id"] for r in agg["results"]} | {
        r["requirement"] for r in agg["results"]
    } | {d["id"] for d in agg["defects"]}
    for found in set(re.findall(r"\b(?:TC|BR|BUG)-\d+\b", report_text)):
        if found not in known_ids:
            warnings.append(f"выдуманный идентификатор {found} — нет в фактах прогона")

    for heading in (RISK_HEADING, VERDICT_HEADING):
        if heading not in report_text:
            warnings.append(f"в отчёте отсутствует раздел «{heading}»")

    # Вердикт в тексте обязан совпасть с тем, что решил код по порогам.
    # Сверяем по смысловым маркерам, а не по буквальной строке: «релиз разрешён
    # с оговорками» и «релиз с оговорками» — это один и тот же вердикт.
    expected_verdict, _ = decide_verdict(agg)
    if VERDICT_HEADING in report_text:
        verdict_text = report_text.split(VERDICT_HEADING, 1)[1].lower()
        has_caveat = "оговорк" in verdict_text
        has_refusal = "не рекоменд" in verdict_text
        actual = (
            "релиз не рекомендуется" if has_refusal
            else "релиз с оговорками" if has_caveat
            else "релиз разрешён"
        )
        if actual != expected_verdict:
            warnings.append(
                f"вывод о релизе расходится с правилами: "
                f"ожидался «{expected_verdict}», в тексте «{actual}»"
            )

    # Транслитерация — проверяем ТОЛЬКО текст модели: фактическую часть отчёта
    # рендерит код, и латиница там легитимна (окружение, URL, названия курсов).
    narrative = report_text.split("## Оценка остаточного риска", 1)
    narrative_text = narrative[1] if len(narrative) > 1 else ""
    allowed = {
        "passed", "failed", "skipped", "major", "minor", "critical", "blocker",
        "http", "https", "otus", "categories", "programming", "catalog",
        "courses", "chrome", "windows", "test", "completion", "report", "lead",
    }
    suspicious = {
        w.lower()
        for w in re.findall(r"\b[A-Za-z]{4,}\b", narrative_text)
        if w.lower() not in allowed
    }
    if suspicious:
        warnings.append(
            "возможная транслитерация вместо русского текста: "
            + ", ".join(sorted(suspicious)[:6])
        )

    return warnings


def pick_backend(choice: str, model: DocGeneratorLLM):
    if choice == "ngram":
        return NgramBackend(model)
    if choice == "ollama":
        return OllamaBackend()
    # auto
    if OllamaBackend.is_available():
        return OllamaBackend()
    print("      Ollama недоступна — переключаюсь на n-gram бэкенд")
    return NgramBackend(model)


def main() -> None:
    parser = argparse.ArgumentParser(description="Генерация тестовой документации")
    parser.add_argument("--backend", choices=["auto", "ollama", "ngram"], default="auto")
    parser.add_argument("--order", type=int, default=3, help="порядок n-грамм")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)

    model = train_model(order=args.order)

    backend = pick_backend(args.backend, model)
    print(f"[2/3] Генерация документов, бэкенд: {backend.name}")

    requirements_text = REQUIREMENTS_FILE.read_text(encoding="utf-8")
    agg = aggregate_results()

    extra_context = {
        "test-cases": f"Бизнес-требования:\n{requirements_text}",
        "checklist": "",
        "test-plan": f"Бизнес-требования:\n{requirements_text}",
        "test-report": facts_block(agg),
    }

    for doc_type, filename in DOCUMENTS.items():
        if doc_type == "test-report":
            # факты — от кода, интерпретация — от модели
            narrative = render_report_narrative(backend, extra_context[doc_type])
            body = render_report_facts(agg) + "\n" + narrative
        else:
            body = backend.render(doc_type, extra_context[doc_type])
        path = OUTPUT_DIR / filename
        path.write_text(body.rstrip() + "\n", encoding="utf-8")
        print(f"      {filename} ({len(body)} символов)")

    print("[3/3] Шлюз качества")
    all_warnings: list[str] = []

    cases_text = (OUTPUT_DIR / DOCUMENTS["test-cases"]).read_text(encoding="utf-8")
    all_warnings += [f"тест-кейсы: {w}" for w in verify_test_cases(cases_text)]

    report_text = (OUTPUT_DIR / DOCUMENTS["test-report"]).read_text(encoding="utf-8")
    all_warnings += [f"отчёт: {w}" for w in verify_report_numbers(report_text, agg)]

    if all_warnings:
        for w in all_warnings:
            print(f"      ВНИМАНИЕ: {w}")
        print("      Документы требуют ручной доработки — см. предупреждения выше.")
    else:
        s = agg["summary"]
        print(f"      OK: 3 кейса (включая негативный); "
              f"{s['passed']} passed / {s['failed']} failed совпадают с фактами")

    print(f"\nГотово. Документы в {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
