import json
import re
import hashlib

from ollama_client import PROJECT_DIR, chat, prepare_ollama

REQUIREMENT_PATH = PROJECT_DIR / "input" / "requirement.md"
OUTPUT_PATH = PROJECT_DIR / "output" / "test_cases.json"
REVIEW_PATH = PROJECT_DIR / "output" / "requirement_review.json"
REVIEW_COMMAND = "python analyze_requirement.py review"
MAX_ATTEMPTS = 3
BASE_SEED = 42
TEXT_FIELDS = ["title", "description", "expected_result"]
LIST_FIELDS = ["preconditions", "steps"]
FOREIGN_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
QUOTED = re.compile(r"[«'\"“]([^«»'\"“”]{3,})[»'\"”]")
PLACEHOLDER = "[текст не указан в требовании]"
INPUT_FIELD = re.compile(r"^- \*\*(.+?)\.\*\*(.*)$", re.MULTILINE)
UNDEFINED = "Поведение не задано требованием, нужно уточнение"
SECURITY_EXPECTED = "Значение не выполняется как код и не меняет запрос к базе, система продолжает работать"
SECURITY_VALUES = {"xss": "<script>alert(1)</script>", "sql": "' OR 1=1 --"}
CHECKS = {
    "пробелы": "пробелы в начале, середине и конце значения",
    "алфавит": "значение кириллицей и значение латиницей",
    "спецсимволы": "значение со спецсимволами !@#$%^&*",
    "длина": "очень длинное значение, строка из 1000 символов",
    "xss": f"ввод {SECURITY_VALUES['xss']}",
    "sql": f"ввод {SECURITY_VALUES['sql']}",
}
MASK_LENGTH_CHECK = "ввод на одну цифру больше, чем вмещает маска"

CHAR_CLASSES = {
    "кириллица": r"[а-яёА-ЯЁ]",
    "латиница строчная": r"[a-z]",
    "латиница заглавная": r"[A-Z]",
    "цифры": r"\d",
    "пробел": r" ",
    "дефис": r"-",
    "точка": r"\.",
    "подчёркивание": r"_",
    "знаки препинания": r"[.,;:!?\-()\"'«»]",
}
ANY_CHARS = "любые символы"
TRIMMED, EDGE_ERROR, NOT_STATED = "обрезаются", "ошибка", "не сказано"
EDGE_SPACES = [TRIMMED, EDGE_ERROR, NOT_STATED]
ACCEPTED, REJECTED, NOT_DEFINED = "принимается", "ошибка", "не задано"
OUTCOME_TEXT = {
    ACCEPTED: "Значение принимается",
    REJECTED: "Появляется сообщение об ошибке",
    NOT_DEFINED: UNDEFINED,
}
DESCRIBED_LENGTH = re.compile(r"^строка из (\d+) символ")

STRING_LIST = {"type": "array", "items": {"type": "string"}}
FORM = "форма"
FORMAT_RULE, OTHER_RULE = "формат значения", "другое правило"


def outline_schema(fields):
    item = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "field": {"type": "string", "enum": fields + [FORM]},
            "rule": {"type": "string", "enum": [FORMAT_RULE, OTHER_RULE]},
        },
        "required": ["title", "field", "rule"],
    }
    return {"type": "object", "properties": {"cases": {"type": "array", "items": item}}, "required": ["cases"]}

CASE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "preconditions": STRING_LIST,
        "steps": STRING_LIST,
        "expected_result": {"type": "string"},
        "boundary_values": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"value": {"type": "string"}, "expected": {"type": "string"}},
                "required": ["value", "expected"],
            },
        },
    },
    "required": TEXT_FIELDS + LIST_FIELDS + ["boundary_values"],
}

RULES_SCHEMA = {
    "type": "object",
    "properties": {
        "min_length": {"type": "integer"},
        "max_length": {"type": "integer"},
        "allowed": {"type": "array", "items": {"type": "string", "enum": list(CHAR_CLASSES) + [ANY_CHARS]}},
        "required": {"type": "array", "items": {"type": "string", "enum": list(CHAR_CLASSES)}},
        "mandatory": {"type": "boolean"},
        "edge_spaces": {"type": "string", "enum": EDGE_SPACES},
        "max_middle_spaces": {"type": "integer"},
        "exact_symbols": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}, "count": {"type": "integer"}},
                "required": ["symbol", "count"],
            },
        },
        "mask": {"type": "string"},
    },
    "required": [
        "mandatory", "min_length", "max_length", "allowed", "required",
        "edge_spaces", "max_middle_spaces", "exact_symbols", "mask",
    ],
}


def input_fields(requirement):
    fields = [name for name, rest in INPUT_FIELD.findall(requirement) if "чекбокс" not in rest.lower()]
    if not fields:
        raise ValueError("В требовании нет полей в формате «- **Имя.** ...»")
    return fields


def field_text(requirement, field):
    match = re.search(rf"^- \*\*{re.escape(field)}\.\*\*.*(?:\n  .*)*", requirement, re.MULTILINE)
    if not match:
        raise ValueError(f"В требовании нет поля «{field}»")
    return match.group(0)


def build_rules_prompt(text, field):
    return f"""Ты senior QA-инженер. Переведи правила поля «{field}» в структуру.
Ничего не придумывай: если правила нет в тексте, ставь значение по умолчанию.

Правила поля:
{text}

Поля структуры:
- mandatory: true, если поле обязательно для заполнения;
- min_length, max_length: границы длины в символах (например, «от 3 до 20» → 3 и 20); если границы нет в тексте — 0;
- allowed: какие классы символов разрешены; если состав не ограничен — ["{ANY_CHARS}"];
- required: классы, которые обязаны встретиться хотя бы раз («минимум одна цифра» → цифры);
- edge_spaces: что происходит с пробелами в начале и конце значения: «обрезаются» — сказано, что их обрезают; «ошибка» — сказано, что пробелы не допускаются; «не сказано» — в тексте об этом ничего нет;
- max_middle_spaces: сколько пробелов разрешено внутри значения; 0, если пробелы не разрешены или не упомянуты;
- exact_symbols: символы, которые должны встретиться точное число раз («ровно один символ @» → @, 1);
- mask: маска ввода, если она есть, иначе пустая строка."""


def validate_rules(rules):
    if rules["max_length"] and rules["min_length"] > rules["max_length"]:
        raise ValueError(f"min_length {rules['min_length']} больше max_length {rules['max_length']}")
    if not rules["allowed"]:
        raise ValueError("пустой список allowed")
    if ANY_CHARS not in rules["allowed"]:
        missing = [name for name in rules["required"] if name not in rules["allowed"]]
        if missing:
            raise ValueError(f"обязательные классы не входят в разрешённые: {missing}")
    for item in rules["exact_symbols"]:
        if len(item["symbol"]) != 1:
            raise ValueError(f"exact_symbols должен содержать один символ, получено {item['symbol']!r}")


def extract_rules(requirement):
    rules = {}
    for field in input_fields(requirement):
        prompt = build_rules_prompt(field_text(requirement, field), field)
        rules[field] = ask_valid(prompt, RULES_SCHEMA, validate_rules, temperature=0)
        if rules[field]["mandatory"]:
            rules[field]["min_length"] = max(rules[field]["min_length"], 1)
    return rules


def describe_rules(field, rules):
    if rules["mask"]:
        parts = [f"маска {rules['mask']}"]
    elif rules["min_length"] and rules["max_length"]:
        parts = [f"длина {rules['min_length']}–{rules['max_length']} символов"]
    elif rules["max_length"]:
        parts = [f"длина до {rules['max_length']} символов"]
    elif rules["min_length"]:
        parts = [f"длина от {rules['min_length']} символов"]
    else:
        parts = ["длина не ограничена"]
    parts.append("разрешены: " + ", ".join(rules["allowed"]))
    if rules["required"]:
        parts.append("обязательны: " + ", ".join(rules["required"]))
    for item in rules["exact_symbols"]:
        parts.append(f"символ {item['symbol']} ровно {item['count']} раз")
    if rules["max_middle_spaces"]:
        parts.append(f"пробелов внутри не больше {rules['max_middle_spaces']}")
    else:
        parts.append("пробелы внутри запрещены")
    parts.append(f"пробелы по краям: {rules['edge_spaces']}")
    return f"{field}: " + "; ".join(parts)


def value_outcome(value, rules):
    described = DESCRIBED_LENGTH.match(value)
    if rules["mask"]:
        if described:
            return NOT_DEFINED
        digits = re.sub(r"\D", "", value)
        prefix = re.sub(r"\D", "", rules["mask"].split("(")[0])
        if digits.startswith(prefix):
            digits = digits[len(prefix):]
        slots = rules["mask"].count(".")
        if len(digits) > slots:
            return NOT_DEFINED
        return ACCEPTED if len(digits) == slots else REJECTED
    if described:
        length = int(described.group(1))
        if not rules["max_length"] and length > max(rules["min_length"], 1):
            return NOT_DEFINED
        too_short = length < rules["min_length"]
        too_long = rules["max_length"] and length > rules["max_length"]
        return REJECTED if too_short or too_long else ACCEPTED
    if rules["edge_spaces"] == TRIMMED:
        value = value.strip(" ")
    elif rules["edge_spaces"] == EDGE_ERROR and value != value.strip(" "):
        return REJECTED
    if len(value) < rules["min_length"] or (rules["max_length"] and len(value) > rules["max_length"]):
        return REJECTED
    if value.count(" ") > rules["max_middle_spaces"]:
        return REJECTED
    for item in rules["exact_symbols"]:
        if value.count(item["symbol"]) != item["count"]:
            return REJECTED
    if ANY_CHARS not in rules["allowed"]:
        allowed = [CHAR_CLASSES[name] for name in rules["allowed"]]
        allowed += [re.escape(item["symbol"]) for item in rules["exact_symbols"]]
        if rules["max_middle_spaces"]:
            allowed.append(" ")
        if re.sub("|".join(allowed), "", value):
            return REJECTED
    for name in rules["required"]:
        if not re.search(CHAR_CLASSES[name], value):
            return REJECTED
    return ACCEPTED


def stated_outcome(text):
    # ponytail: ищем исход по ключевым словам; если модель начнёт писать иначе, расширить список
    lowered = text.lower()
    if "не задан" in lowered or "уточнени" in lowered:
        return NOT_DEFINED
    if "ошибк" in lowered or "не прин" in lowered or "не валид" in lowered:
        return REJECTED
    return ACCEPTED


def corrected_outcome(value, stated_text, rules, format_only):
    if any(security in value for security in SECURITY_VALUES.values()):
        return None
    computed = value_outcome(value, rules)
    if computed == ACCEPTED and not format_only:
        return None
    return computed if stated_outcome(stated_text) != computed else None


def apply_rules(case, rules, format_only):
    fixes = 0
    for item in case["boundary_values"]:
        computed = corrected_outcome(item["value"], item["expected"], rules, format_only)
        if computed:
            item["expected"] = OUTCOME_TEXT[computed]
            fixes += 1
    steps = " ".join(case["steps"])
    tested = next((item for item in case["boundary_values"] if item["value"].strip() and item["value"] in steps), None)
    if tested is None and case["boundary_values"] and (format_only or len(case["boundary_values"]) == 1):
        tested = case["boundary_values"][0]
    if tested:
        computed = corrected_outcome(tested["value"], case["expected_result"], rules, format_only)
        if computed:
            case["expected_result"] = OUTCOME_TEXT[computed]
            fixes += 1
    return fixes

def build_outline_prompt(requirement, count, existing):
    return f"""Ты senior QA-инженер.

Контекст (требование):
{requirement}

Техника: применяй классы эквивалентности и анализ граничных значений.
Включи позитивные, негативные и граничные проверки.

Формат: в поле cases верни ровно {count} разных тест-кейсов. Для каждого:
- title: короткое название;
- field: поле, которое проверяет кейс, или «{FORM}», если кейс проверяет форму целиком;
- rule: «{FORMAT_RULE}», если кейс проверяет только допустимость введённого значения (длина, символы, маска);
  «{OTHER_RULE}», если результат зависит от другого: уникальность, чекбокс, поведение формы.
Правила:
- каждое название описывает одну проверку одного правила;
- названия не повторяют одну и ту же проверку другими словами;
- для каждого числового ограничения длины есть отдельная проверка границ;
- есть хотя бы одна позитивная проверка и проверки уникальности, если они есть в требовании.

Эти проверки уже есть, не повторяй их:
{chr(10).join(existing)}

Ограничения: пиши только на русском языке. Не придумывай правил, которых нет в требовании."""


def build_case_prompt(requirement, title):
    return f"""Ты senior QA-инженер.

Контекст (требование):
{requirement}

Задача: напиши один тест-кейс с названием «{title}».

Техника: применяй классы эквивалентности и анализ граничных значений.
Формат полей:
- title: название тест-кейса;
- description: что проверяем и зачем;
- preconditions: условия перед началом теста;
- steps: действия для одной проверки, все остальные поля заполнены допустимыми данными;
- expected_result: наблюдаемый результат одной проверки;
- boundary_values: проверяемые значения только того поля, которое проверяет этот тест; value — конкретное значение, которое вводит тестировщик, expected — ожидаемый результат для этого значения.

Как записывать boundary_values при числовом диапазоне: значение на единицу меньше минимума, минимум, максимум, значение на единицу больше максимума.
Пример для другого поля «Возраст» с диапазоном от 18 до 65:
[{{"value": "17", "expected": "ошибка"}}, {{"value": "18", "expected": "принимается"}}, {{"value": "65", "expected": "принимается"}}, {{"value": "66", "expected": "ошибка"}}]
Если числовых границ нет, укажи пограничные случаи этого поля: пустое значение, неверный формат.
Значение из шагов теста должно быть в boundary_values.

Ограничения:
- пиши только на русском языке;
- не придумывай правил, которых нет в требовании;
- текст сообщения в кавычках пиши только дословно из требования; если в требовании текста нет, пиши «появляется сообщение об ошибке» без кавычек и без своего текста;
- если требование не задаёт поведение для этой проверки, в expected_result напиши ровно: {UNDEFINED};
- значение длиннее 30 символов пиши только описанием «строка из N символов» и не приводи к нему пример."""


def validate_outline(data, count):
    titles = [item["title"].strip() for item in data["cases"] if item["title"].strip()]
    if len(set(titles)) < count:
        raise ValueError(f"нужно {count} разных названий, получено {len(set(titles))}")


def validate_case(case, check=None):
    for field in TEXT_FIELDS:
        if not case[field].strip():
            raise ValueError(f"пустое поле {field}")
    for field in LIST_FIELDS:
        if not case[field] or not all(item.strip() for item in case[field]):
            raise ValueError(f"пустой список или элемент в поле {field}")
    if not case["boundary_values"]:
        raise ValueError("пустой список boundary_values")
    for item in case["boundary_values"]:
        if not item["expected"].strip():
            raise ValueError("пустой expected в boundary_values")
    if FOREIGN_CHARS.search(json.dumps(case, ensure_ascii=False)):
        raise ValueError("в тексте есть символы другого языка")
    if check == "длина" and any(re.fullmatch(r"\d{1,3}", item["value"]) for item in case["boundary_values"]):
        raise ValueError("длину значения пиши описанием «строка из N символов», а не числом")
    if check in SECURITY_VALUES and not any(SECURITY_VALUES[check] in step for step in case["steps"]):
        raise ValueError(f"в шагах нет значения {SECURITY_VALUES[check]}")


def remove_invented_quotes(text, requirement):
    allowed = " ".join(requirement.split())

    def replace(match):
        quote = " ".join(match.group(1).split()).rstrip(".")
        return match.group(0) if quote in allowed else PLACEHOLDER

    return QUOTED.sub(replace, text)


def ask_valid(prompt, schema, validate, temperature=0.2):
    for attempt in range(MAX_ATTEMPTS):
        try:
            data = chat(prompt, schema=schema, temperature=temperature, seed=BASE_SEED + attempt)
            validate(data)
            return data
        except (ValueError, KeyError) as error:
            print(f"  попытка {attempt + 1}/{MAX_ATTEMPTS} не прошла: {error}")
    raise RuntimeError(f"Модель не дала корректный ответ за {MAX_ATTEMPTS} попытки")


def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_review(requirement):
    if not REVIEW_PATH.exists():
        raise SystemExit(f"Требование не проверено. Запусти: {REVIEW_COMMAND}")
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    if review.get("requirement_sha256") != fingerprint(requirement):
        raise SystemExit(f"Требование изменилось после проверки. Запусти: {REVIEW_COMMAND}")
    if "field_rules" not in review:
        raise SystemExit(f"В ревью нет подтверждённых правил полей. Запусти: {REVIEW_COMMAND}")
    return review


def suite_coverage(cases, requirement):
    required = {(field, check) for field in input_fields(requirement) for check in CHECKS}
    covered = {(case["field"], case["check"]) for case in cases}
    missing = sorted(required - covered)
    return {
        "required": len(required),
        "covered": len(required) - len(missing),
        "missing": [f"{field}: {check}" for field, check in missing],
    }


def check_description(check, description, rules):
    if check == "длина" and rules and rules["mask"]:
        return MASK_LENGTH_CHECK
    return description


def generate_cases(requirement, field_rules, free_count=6):
    fields = input_fields(requirement)
    plan = [
        (field, check, f"{field}: {check_description(check, description, field_rules.get(field))}", True)
        for field in fields
        for check, description in CHECKS.items()
    ]
    outline = ask_valid(
        build_outline_prompt(requirement, free_count, [title for _, _, title, _ in plan]),
        outline_schema(fields),
        lambda data: validate_outline(data, free_count),
    )
    unique = {item["title"].strip(): item for item in outline["cases"] if item["title"].strip()}
    plan += [
        (item["field"] if item["field"] in fields else None, None, title, item["rule"] == FORMAT_RULE)
        for title, item in list(unique.items())[:free_count]
    ]

    cases = []
    for number, (field, check, title, format_only) in enumerate(plan, start=1):
        print(f"[{number}/{len(plan)}] {title}")
        try:
            case = ask_valid(
                build_case_prompt(requirement, title),
                CASE_SCHEMA,
                lambda data: validate_case(data, check),
            )
        except RuntimeError as error:
            print(f"  кейс пропущен: {error}")
            continue
        if check in SECURITY_VALUES:
            case["expected_result"] = SECURITY_EXPECTED
        else:
            case["expected_result"] = remove_invented_quotes(case["expected_result"], requirement)
        for item in case["boundary_values"]:
            if check in SECURITY_VALUES and SECURITY_VALUES[check] in item["value"]:
                item["expected"] = SECURITY_EXPECTED
            else:
                item["expected"] = remove_invented_quotes(item["expected"], requirement)
        rules = field_rules.get(field)
        fixes = apply_rules(case, rules, format_only) if rules else 0
        if fixes:
            print(f"  исправлено по правилам поля: {fixes}")
        cases.append({
            "id": f"TC-{len(cases) + 1:03d}", "field": field, "check": check,
            "format_check": format_only, "rule_fixes": fixes, **case,
        })
    return cases


if __name__ == "__main__":
    requirement = REQUIREMENT_PATH.read_text(encoding="utf-8")
    review = check_review(requirement)
    print(f"Требование проверено: {review['status']}, принятых рисков {len(review['accepted_risks'])}")
    prepare_ollama()
    cases = generate_cases(requirement, review["field_rules"])
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Сохранено кейсов: {len(cases)} → {OUTPUT_PATH}")
    print("Покрытие обязательных проверок:", suite_coverage(cases, requirement))

