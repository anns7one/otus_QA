"""Шаг 8: сборка итогового отчёта. Формат: тесты по приоритетам
от высшего к низшему, дублирующие шаги, дублирующие тесты, «Не найдено» если
список пуст."""
PRIORITY_ORDER = ["High", "Medium", "Low", None]
PRIORITY_LABEL = {"High": "HIGH", "Medium": "MEDIUM", "Low": "LOW", None: "БЕЗ ПРИВЯЗКИ К ТРЕБОВАНИЮ"}


def render_report(tests_with_quality: list[dict], duplicate_steps: list[dict],
                   duplicate_tests: list, coverage, requirements: list[dict]) -> str:
    lines = ["# Отчёт оптимизатора автотестов", ""]

    lines.append("## Тесты по приоритетам")
    lines.append("")
    grouped = {p: [] for p in PRIORITY_ORDER}
    for item in tests_with_quality:
        grouped[item["priority"]].append(item)
    for prio in PRIORITY_ORDER:
        items = grouped[prio]
        lines.append(f"### {PRIORITY_LABEL[prio]} ({len(items)})")
        if not items:
            lines.append("Не найдено")
        else:
            for item in sorted(items, key=lambda x: -x["quality"]):
                req = ", ".join(item["requirements"]) or "-"
                lines.append(f"- `{item['name']}` — качество {item['quality']:.1f}, требование: {req}")
        lines.append("")

    lines.append("## Дублирующие шаги")
    lines.append("")
    if not duplicate_steps:
        lines.append("Не найдено")
    else:
        for g in duplicate_steps:
            lines.append(f"- `{g['step']}` — в тестах: {', '.join(g['tests'])}")
    lines.append("")

    lines.append("## Дублирующие/похожие тесты")
    lines.append("")
    if not duplicate_tests:
        lines.append("Не найдено")
    else:
        for p in duplicate_tests:
            lines.append(f"- **{p.kind}** `{p.a}` <-> `{p.b}` (score={p.score:.3f}) — {p.reason}")
    lines.append("")

    lines.append("## Покрытие требований")
    lines.append("")
    lines.append(
        f"Покрыто {len(coverage.covered_ids)} из {coverage.total} "
        f"({coverage.percent}%), взвешенно по приоритетам — {coverage.weighted_percent}%."
    )
    if coverage.uncovered_ids:
        by_id = {r["id"]: r for r in requirements}
        lines.append("")
        lines.append("Непокрытые требования:")
        for rid in sorted(coverage.uncovered_ids):
            r = by_id[rid]
            lines.append(f"- `{rid}` ({r['priority']}) — {r['text']}")
    lines.append("")

    return "\n".join(lines)
