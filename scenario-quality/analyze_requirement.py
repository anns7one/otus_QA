import argparse
import json
import re
from datetime import datetime

from generate_cases import ask_valid
from ollama_client import PROJECT_DIR, prepare_ollama

GOLDEN_DIR = PROJECT_DIR / "data" / "analyzer_golden"
REQUIREMENT_PATH = PROJECT_DIR / "input" / "requirement.md"
OUTPUT_DIR = PROJECT_DIR / "output"
PROGRESS_PATH = OUTPUT_DIR / "analyzer_progress.jsonl"
REVIEW_PATH = OUTPUT_DIR / "requirement_review.json"
CURRENT_PROMPT = "v1"
SECURITY_WORDS = r"xss|инъекц|вредонос|скрипт"
MANDATORY = "обязательная проверка"
ACCEPT_COMMAND = "принять"

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "quote": {"type": "string"},
                    "problem": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["criterion", "quote", "problem", "question"],
            },
        }
    },
    "required": ["findings"],
}

FORMAT = """
Формат: для каждой проблемы верни criterion (критерий), quote (дословная цитата пункта требования), problem (в чём проблема), question (конкретный вопрос автору требования).
Пиши только на русском языке. Не придумывай правил, которых нет в требовании."""

INSTRUCTIONS = {
    "v1": "Найди проблемы качества требования.",
    "v2": """Критерии качества:
- однозначность: у формулировки только одно прочтение; если их несколько, покажи оба;
- полнота: заданы форматы, лимиты и поведение при ошибках;
- непротиворечивость: пункты не противоречат друг другу;
- проверяемость: результат можно однозначно проверить тестом;
- атомарность: один пункт описывает одно правило.

Проверь каждый пункт требования по всем критериям.

Для КАЖДОГО поля ввода отдельно задай вопросы:
- какие символы и алфавиты допустимы, что с пробелами и спецсимволами;
- минимальная и максимальная длина;
- какой текст ошибки при неверном вводе;
- что будет при вводе вредоносного кода (XSS, SQL-инъекция).
""",
    "v3": """Читай текст требования и ищи только проблемы конкретных формулировок:
- размытые слова без числа или точного значения;
- два пункта, которые нельзя выполнить одновременно;
- пункт, где результат описан несколькими вариантами на выбор;
- сценарий, упомянутый в тексте, для которого не описан исход: неверное значение, пустой результат, сбой.

Правила:
- Вопрос называет конкретное слово или поле из цитаты. Вопрос, который подошёл бы к другому пункту, не пиши.
- Одна проблема — одна находка. Не повторяй вопросы.
- Если пункт написан точно, не пиши по нему ничего.

Пример для другого требования, «Гость отменяет бронь незадолго до визита. Столик вмещает 2-8 гостей»:
{"findings": [
 {"criterion": "однозначность", "quote": "незадолго до визита", "problem": "«незадолго» не задано числом", "question": "За сколько часов до визита ещё можно отменить бронь?"},
 {"criterion": "полнота", "quote": "Столик вмещает 2-8 гостей", "problem": "не описан исход для значения вне диапазона", "question": "Что увидит гость, если укажет 1 или 9 гостей?"}
]}
""",
}


def build_prompt(requirement, version):
    return f"""Ты QA lead. Проанализируй требование на тестопригодность.

Требование:
{requirement}

{INSTRUCTIONS[version]}
{FORMAT}"""


def normalize(text):
    return " ".join(text.split()).lower()


def clean_findings(findings, requirement):
    allowed = normalize(requirement)
    seen_questions = set()
    kept = []
    bad_quotes = duplicates = 0
    for finding in findings:
        quote = normalize(finding["quote"]).strip(" .`*-")
        question = normalize(finding["question"])
        if not quote or quote not in allowed:
            bad_quotes += 1
        elif question in seen_questions:
            duplicates += 1
        else:
            seen_questions.add(question)
            kept.append(finding)
    return kept, bad_quotes, duplicates


def mandatory_findings(requirement):
    if re.search(SECURITY_WORDS, normalize(requirement)):
        return []
    return [{
        "criterion": MANDATORY,
        "quote": "",
        "problem": "В требовании нет правил для вредоносного ввода",
        "question": "Как система должна обрабатывать XSS и SQL-инъекции в полях ввода?",
    }]


def analyze(requirement, version=CURRENT_PROMPT):
    data = ask_valid(build_prompt(requirement, version), FINDINGS_SCHEMA, lambda _: None, temperature=0)
    findings, bad_quotes, duplicates = clean_findings(data["findings"], requirement)
    return findings + mandatory_findings(requirement), bad_quotes, duplicates


def matches(finding, defect):
    text = normalize(finding["problem"] + " " + finding["question"])
    return bool(re.search(defect["pattern"], text)) and defect["field"].lower() in normalize(finding["quote"])


def evaluate(version, split="dev"):
    golden = json.loads((GOLDEN_DIR / "defects.json").read_text(encoding="utf-8"))
    selected = {req_id: item for req_id, item in golden.items() if item["split"] == split}
    all_findings = {}
    missed = []
    found = total = findings_total = findings_matched = bad_quotes_total = duplicates_total = llm_found = 0

    for req_id, item in selected.items():
        requirement = (GOLDEN_DIR / f"{req_id}.md").read_text(encoding="utf-8")
        findings, bad_quotes, duplicates = analyze(requirement, version)
        all_findings[req_id] = findings
        bad_quotes_total += bad_quotes
        duplicates_total += duplicates
        findings_total += len(findings)
        findings_matched += sum(any(matches(f, d) for d in item["defects"]) for f in findings)
        hits = [d["id"] for d in item["defects"] if any(matches(f, d) for f in findings)]
        found += len(hits)
        llm_only = [f for f in findings if f["criterion"] != MANDATORY]
        llm_found += sum(any(matches(f, d) for f in llm_only) for d in item["defects"])
        total += len(item["defects"])
        missed += [f"{req_id}:{d['id']}" for d in item["defects"] if d["id"] not in hits]
        print(f"{req_id}: найдено дефектов {len(hits)}/{len(item['defects'])}, находок {len(findings)}, неверных цитат {bad_quotes}, дублей {duplicates}")

    record = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "prompt": version,
        "split": split,
        "defects_found": found,
        "defects_total": total,
        "recall": round(found / total, 3),
        "recall_llm_only": round(llm_found / total, 3),
        "findings": findings_total,
        "findings_matched": findings_matched,
        "bad_quotes": bad_quotes_total,
        "duplicates": duplicates_total,
        "missed": missed,
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    with PROGRESS_PATH.open("a", encoding="utf-8") as progress:
        progress.write(json.dumps(record, ensure_ascii=False) + "\n")
    findings_path = OUTPUT_DIR / f"analyzer_findings_{version}.json"
    findings_path.write_text(json.dumps(all_findings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Recall {record['recall']:.0%} ({found}/{total}), находок {findings_total}, совпали с дефектами {findings_matched}")
    return record


def save_review(status, findings):
    OUTPUT_DIR.mkdir(exist_ok=True)
    review = {"status": status, "accepted_risks": findings}
    REVIEW_PATH.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Статус требования: {status} → {REVIEW_PATH}")


def review():
    prepare_ollama()
    while True:
        requirement = REQUIREMENT_PATH.read_text(encoding="utf-8")
        findings, _, _ = analyze(requirement)
        if not findings:
            save_review("passed", [])
            return
        for number, finding in enumerate(findings, start=1):
            print(f"\n{number}. [{finding['criterion']}] {finding['quote']}")
            print(f"   Проблема: {finding['problem']}")
            print(f"   Вопрос: {finding['question']}")

        answer = input(f"\nВведите уточнение к требованию или «{ACCEPT_COMMAND}», чтобы принять риски: ").strip()
        if answer.lower() == ACCEPT_COMMAND:
            save_review("accepted_risks", findings)
            return
        if answer:
            with REQUIREMENT_PATH.open("a", encoding="utf-8") as file:
                file.write(f"\n- Уточнение: {answer}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Анализ качества требования")
    parser.add_argument("command", choices=["review", "evaluate"])
    parser.add_argument("--prompt", default=CURRENT_PROMPT, choices=sorted(INSTRUCTIONS))
    parser.add_argument("--split", default="dev", choices=["dev", "holdout"])
    args = parser.parse_args()
    if args.command == "review":
        review()
    else:
        prepare_ollama()
        evaluate(args.prompt, args.split)
