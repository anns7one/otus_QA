import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from build_dataset import METRICS
from ollama_client import MODEL, PROJECT_DIR

OUTPUT_DIR = PROJECT_DIR / "output"
RESULTS_PATH = OUTPUT_DIR / "results.json"
REPORT_PATH = OUTPUT_DIR / "report.md"
PLOTS_DIR = OUTPUT_DIR / "plots"
METRIC_TITLES = {
    "readability": "Читаемость",
    "goal_clarity": "Чёткость целей",
    "coverage": "Покрытие сценариев",
    "consistency": "Согласованность",
}
INK, INK_MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834"]


def quality(score, passed):
    if not passed:
        return "Низкое"
    return "Высокое" if score >= 0.75 else "Среднее"


def build_results(cases, predictions, review, coverage, threshold):
    items = []
    for case, metrics in zip(cases, predictions):
        score = sum(metrics.values()) / len(metrics)
        passed = all(value >= threshold for value in metrics.values())
        items.append({
            "id": case["id"],
            "title": case["title"],
            "metrics": {name: round(value, 3) for name, value in metrics.items()},
            "score": round(score, 3),
            "quality": quality(score, passed),
            "passed": passed,
            "rule_fixes": case.get("rule_fixes", 0),
        })
    passed = sum(item["passed"] for item in items)
    return {
        "generator_model": MODEL,
        "threshold": threshold,
        "summary": {"total": len(items), "passed": passed, "failed": len(items) - passed},
        "suite_coverage": coverage,
        "accepted_risks": len(review["accepted_risks"]),
        "scenarios": items,
    }


def style():
    sns.set_theme(style="white", rc={
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": INK_MUTED,
        "text.color": INK, "axes.labelcolor": INK_MUTED, "xtick.color": INK_MUTED, "ytick.color": INK_MUTED,
    })


def save(figure, name):
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(PLOTS_DIR / name, dpi=150)
    plt.close(figure)
    return f"plots/{name}"


def plot_scores(results):
    figure, axis = plt.subplots(figsize=(7, 4))
    sns.histplot([item["score"] for item in results["scenarios"]], bins=10, binrange=(0, 1), color=SERIES[0], ax=axis)
    axis.axvline(results["threshold"], color=INK_MUTED, linestyle="--", linewidth=1)
    axis.text(results["threshold"], axis.get_ylim()[1] * 0.95, " порог каждой метрики", color=INK_MUTED, va="top")
    axis.set(title="Распределение итоговых оценок", xlabel="Оценка (среднее 4 метрик)", ylabel="Сценариев")
    sns.despine()
    return save(figure, "scores.png")


def plot_heatmap(results):
    rows = results["scenarios"]
    data = [[item["metrics"][metric] for metric in METRICS] for item in rows]
    figure, axis = plt.subplots(figsize=(7, max(4, len(rows) * 0.28)))
    sns.heatmap(data, vmin=0, vmax=1, cmap="Blues", linewidths=1, linecolor=SURFACE, annot=True, fmt=".2f",
                annot_kws={"size": 7}, xticklabels=[METRIC_TITLES[m] for m in METRICS],
                yticklabels=[item["id"] for item in rows], cbar_kws={"label": "Вероятность «хорошо»"}, ax=axis)
    axis.set(title="Оценка каждого сценария по метрикам")
    return save(figure, "heatmap.png")


def plot_means(results):
    means = [sum(item["metrics"][metric] for item in results["scenarios"]) / len(results["scenarios"]) for metric in METRICS]
    figure, axis = plt.subplots(figsize=(7, 3.5))
    sns.barplot(x=means, y=[METRIC_TITLES[m] for m in METRICS], color=SERIES[0], width=0.5, ax=axis)
    for index, value in enumerate(means):
        axis.text(value + 0.01, index, f"{value:.2f}", va="center", color=INK)
    axis.set(xlim=(0, 1.08), title="Средняя оценка по метрикам", xlabel="Среднее", ylabel="")
    sns.despine()
    return save(figure, "metric_means.png")


def plot_training(history):
    figure, axis = plt.subplots(figsize=(7, 4))
    epochs = [row["epoch"] for row in history]
    for key, label, color in [("train_loss", "обучение", SERIES[0]), ("val_loss", "валидация", SERIES[1])]:
        values = [row[key] for row in history]
        axis.plot(epochs, values, color=color, linewidth=2, label=label)
        axis.text(epochs[-1], values[-1], f" {label}", color=INK_MUTED, va="center")
    axis.set(title="Кривые обучения", xlabel="Эпоха", ylabel="BCE loss")
    axis.legend(frameon=False)
    sns.despine()
    return save(figure, "training.png")


def escape(text):
    return text.replace("|", "\\|").replace("\n", " ")


def write_markdown(results, plot_path):
    summary = results["summary"]
    lines = [
        "# Отчёт о тестировании сценариев",
        "",
        "## Общая информация",
        f"- Количество сценариев: {summary['total']}",
        f"- Успешные: {summary['passed']}",
        f"- Неуспешные: {summary['failed']}",
        "",
        "## Распределение качества",
        f"[Визуальный отчёт]({plot_path})",
        "",
        "## Список сценариев",
        "",
        "| Описание | Качество | Оценка |",
        "|---|---|---|",
    ]
    lines += [f"| {escape(item['id'] + ' ' + item['title'])} | {item['quality']} | {item['score']:.2f} |"
              for item in results["scenarios"]]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(cases, predictions, review, coverage, training):
    style()
    results = build_results(cases, predictions, review, coverage, training["threshold"])
    results["plots"] = [plot_scores(results), plot_heatmap(results), plot_means(results), plot_training(training["history"])]
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(results, results["plots"][0])
    print(f"Отчёт: {REPORT_PATH}, результаты: {RESULTS_PATH}")
    return results
