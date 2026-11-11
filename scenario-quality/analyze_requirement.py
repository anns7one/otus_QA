import argparse
import json
import re
from datetime import datetime
from generate_cases import INPUT_FIELD, REVIEW_PATH, ask_valid, describe_rules, extract_rules, fingerprint
from ollama_client import PROJECT_DIR, prepare_ollama

GOLDEN_DIR = PROJECT_DIR / "data" / "analyzer_golden"
REQUIREMENT_PATH = PROJECT_DIR / "input" / "requirement.md"
OUTPUT_DIR = PROJECT_DIR / "output"
PROGRESS_PATH = OUTPUT_DIR / "analyzer_progress.jsonl"
CURRENT_PROMPT = "v1"
SECURITY_DEFECT_IDS = {"security", "malicious-file"}
ACCEPT_COMMANDS = ("принять", "нет")
CONFIRM_YES = "да"
CHECK_TITLES = {
    "general": "Общий анализ требования",
    "vague": "Неизмеримая формулировка",
    "outcome": "Не определён ожидаемый результат",
    "contradiction": "Противоречие между пунктами",
    "alternatives": "Неоднозначный ожидаемый результат",
    "security": "Не определена обработка вредоносного ввода",
}
CRITERIA = ["однозначность", "полнота", "непротиворечивость", "проверяемость", "атомарность"]
CHECK_CRITERION = {
    "vague": "однозначность",
    "outcome": "полнота",
    "contradiction": "непротиворечивость",
    "alternatives": "однозначность",
    "security": "безопасность",
}
OTHER_FIELD = "Поведение и общие пункты"
ALL_FIELDS = "Все поля"

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string", "enum": CRITERIA},
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

SECURITY_SCHEMA = {
    "type": "object",
    "properties": {"has_rules": {"type": "boolean"}, "quote": {"type": "string"}},
    "required": ["has_rules", "quote"],
}

SECURITY_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "question": {"type": "string"},
    },
    "required": ["problem", "question"],
}

FORMAT = f"""
Формат: для каждой проблемы верни criterion (критерий качества: {", ".join(CRITERIA)}), quote (дословная цитата пункта требования), problem (в чём проблема), question (конкретный вопрос автору требования).
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


NARROW_CHECKS = {
    "vague": "размытые слова и оценки без числа или точного значения (например «оперативно», «значительный», «по возможности»), которые нельзя проверить тестом",
    "outcome": "действия пользователя и входные данные, для которых не описан результат: неверное или несуществующее значение, недопустимое сочетание значений, пустой результат, отказ или сбой системы",
    "contradiction": "пункты требования, которые противоречат друг другу; в quote процитируй один из пунктов, в problem назови оба",
    "alternatives": "пункты, где результат описан несколькими вариантами на выбор («или», «в зависимости от»), поэтому ожидаемый результат теста нельзя записать однозначно",
}


def build_narrow_prompt(requirement, description):
    return f"""Ты QA lead. Проверь требование только на один тип проблем.

Требование:
{requirement}

Тип проблем: {description}.
Если таких проблем нет, верни пустой список findings.
{FORMAT}"""


def normalize(text):
    return " ".join(re.sub(r"[*`]", "", text).split()).lower()


def quote_in_requirement(quote, allowed):
    parts = [normalize(part).strip(' .`*-"') for part in re.split(r'\n|"\s*и\s*"', quote)]
    parts = [part for part in parts if part]
    return bool(parts) and all(part in allowed for part in parts)


def clean_findings(findings, requirement):
    allowed = normalize(requirement)
    seen_questions = set()
    kept = []
    bad_quotes = duplicates = 0
    for finding in findings:
        question = normalize(finding["question"])
        if not quote_in_requirement(finding["quote"], allowed):
            bad_quotes += 1
        elif question in seen_questions:
            duplicates += 1
        else:
            seen_questions.add(question)
            kept.append(finding)
    return kept, bad_quotes, duplicates


def build_security_prompt(requirement):
    return f"""Ты специалист по безопасности веб-приложений.

Требование:
{requirement}

Есть ли в требовании явные правила обработки вредоносного ввода: XSS, SQL-инъекции, HTML и скрипты в полях, проверка содержимого загружаемых файлов?
Если есть, верни has_rules true и в quote дословную цитату пункта с этим правилом.
Если нет, верни has_rules false и пустой quote.
Обычная валидация формата (длина, маска, допустимые символы) не считается правилом безопасности."""


def build_security_findings_prompt(requirement):
    return f"""Ты специалист по безопасности веб-приложений.

Требование:
{requirement}

В требовании нет правил обработки вредоносного ввода ни для одного поля.
Напиши ОДНУ общую находку на всё требование:
- problem: какой вредоносный ввод (XSS, SQL-инъекции) не описан, перечисли все поля ввода и загрузки файлов, для которых это опасно, и чем это грозит;
- question: один конкретный вопрос автору требования.
Пиши только на русском языке."""


def validate_security_finding(data):
    if not data["problem"].strip() or not data["question"].strip():
        raise ValueError("пустая проблема или вопрос в находке безопасности")


def security_findings(requirement):
    decision = ask_valid(build_security_prompt(requirement), SECURITY_SCHEMA, lambda _: None, temperature=0)
    quote = normalize(decision["quote"]).strip(" .`*-")
    if decision["has_rules"] and quote and quote in normalize(requirement):
        return []
    finding = ask_valid(build_security_findings_prompt(requirement), SECURITY_FINDING_SCHEMA, validate_security_finding, temperature=0)
    return [{**finding, "criterion": full_criterion(CHECK_CRITERION["security"], "security"), "quote": "", "check": "security"}]


def full_criterion(attribute, check):
    return f"{attribute.capitalize()}: {CHECK_TITLES[check][0].lower()}{CHECK_TITLES[check][1:]}"


def analyze(requirement, version=CURRENT_PROMPT):
    data = ask_valid(build_prompt(requirement, version), FINDINGS_SCHEMA, lambda _: None, temperature=0)
    raw = [{**finding, "criterion": full_criterion(finding["criterion"], "general"), "check": "general"}
           for finding in data["findings"]]
    for check, description in NARROW_CHECKS.items():
        data = ask_valid(build_narrow_prompt(requirement, description), FINDINGS_SCHEMA, lambda _: None, temperature=0)
        raw += [{**finding, "criterion": full_criterion(CHECK_CRITERION[check], check), "check": check}
                for finding in data["findings"]]
    findings, bad_quotes, duplicates = clean_findings(raw, requirement)
    return findings + security_findings(requirement), bad_quotes, duplicates


def matches(finding, defect):
    text = normalize(finding["problem"] + " " + finding["question"])
    return bool(re.search(defect["pattern"], text)) and defect["field"].lower() in normalize(finding["quote"])


def evaluate(version, split="dev"):
    golden = json.loads((GOLDEN_DIR / "defects.json").read_text(encoding="utf-8"))
    selected = {req_id: item for req_id, item in golden.items() if item["split"] == split}
    all_findings = {}
    missed = []
    found = total = findings_total = findings_matched = bad_quotes_total = duplicates_total = 0
    security_gaps = security_hits = security_false_alarms = 0

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
        has_gap = any(d["id"] in SECURITY_DEFECT_IDS for d in item["defects"])
        flagged = any(f.get("check") == "security" for f in findings)
        security_gaps += has_gap
        security_hits += has_gap and flagged
        security_false_alarms += flagged and not has_gap
        total += len(item["defects"])
        missed += [f"{req_id}:{d['id']}" for d in item["defects"] if d["id"] not in hits]
        title = requirement.splitlines()[0].split(" - ", 1)[-1].strip()
        print(f"{req_id} ({title}): найдено дефектов {len(hits)}/{len(item['defects'])}, находок {len(findings)}, неверных цитат {bad_quotes}, дублей {duplicates}")

    record = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "prompt": version,
        "narrow_checks": list(NARROW_CHECKS),
        "split": split,
        "defects_found": found,
        "defects_total": total,
        "recall": round(found / total, 3),
        "security_found": security_hits,
        "security_gaps": security_gaps,
        "security_false_alarms": security_false_alarms,
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
    print(f"Безопасность: найдено {security_hits}/{security_gaps}, ложных тревог {security_false_alarms}")
    return record


def field_items(requirement):
    items = []
    for line in requirement.splitlines():
        match = INPUT_FIELD.match(line)
        if match:
            items.append([match.group(1), line])
        elif items and line.startswith("  "):
            items[-1][1] += " " + line
    return [(name, normalize(text)) for name, text in items]


def first_quote_part(finding):
    return normalize(re.split(r'\n|"\s*и\s*"', finding["quote"])[0]).strip(' .`*-"')


def field_of(finding, requirement):
    if not finding["quote"].strip():
        return ALL_FIELDS
    first = first_quote_part(finding)
    names = [name for name, text in field_items(requirement) if first in text]
    return names[0] if len(names) == 1 else OTHER_FIELD


def sort_findings(findings, requirement):
    fields = [name for name, _ in field_items(requirement)]
    position = {name: index for index, name in enumerate(fields + [OTHER_FIELD, ALL_FIELDS])}
    checks = list(CHECK_TITLES)
    text = normalize(requirement)
    for finding in findings:
        finding["field"] = field_of(finding, requirement)
    return sorted(findings, key=lambda finding: (
        position[finding["field"]],
        text.find(first_quote_part(finding)),
        checks.index(finding["check"]),
    ))


def print_findings(findings):
    field = None
    for number, finding in enumerate(findings, start=1):
        if finding["field"] != field:
            field = finding["field"]
            print(f"\n=== {field} ===")
        print(f"{number}. [{finding['criterion']}] {finding['quote']}")
        print(f"   Проблема: {finding['problem']}")
        print(f"   Вопрос: {finding['question']}")


def confirm_rules(requirement):
    print("\nРазбираю правила полей (около 4 секунд на поле)...")
    rules = extract_rules(requirement)
    print("Правила полей, которые будут использованы при генерации:")
    for field, field_rules in rules.items():
        print(f"- {describe_rules(field, field_rules)}")
    answer = input(f"\nПравила верны? ({CONFIRM_YES} / нет): ").strip().lower()
    if answer != CONFIRM_YES:
        print("Ревью не сохранено. Уточни формулировки полей в требовании и запусти ревью заново.")
        return None
    return rules


def save_review(status, findings, requirement, rules):
    OUTPUT_DIR.mkdir(exist_ok=True)
    review = {
        "status": status,
        "requirement_sha256": fingerprint(requirement),
        "accepted_risks": findings,
        "field_rules": rules,
    }
    REVIEW_PATH.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Статус требования: {status} → {REVIEW_PATH}")


def review():
    prepare_ollama()
    while True:
        requirement = REQUIREMENT_PATH.read_text(encoding="utf-8")
        print("\nАнализирую требование (1–2 минуты)...")
        findings, _, _ = analyze(requirement)
        if findings:
            findings = sort_findings(findings, requirement)
            print_findings(findings)
            answer = ask_next_step()
        if not findings or answer in ACCEPT_COMMANDS:
            rules = confirm_rules(requirement)
            if rules is not None:
                save_review("accepted_risks" if findings else "passed", findings, requirement, rules)
            return


def ask_next_step():
    while True:
        answer = input(
            f"\nИсправь поля в {REQUIREMENT_PATH.name} и нажми Enter, чтобы проверить заново, "
            "или введи «принять» / «нет», чтобы принять риски: "
        ).strip().lower()
        if not answer or answer in ACCEPT_COMMANDS:
            return answer
        print("Уточнения пиши прямо в поля требования, здесь только Enter или «принять» / «нет».")


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
