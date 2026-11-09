import json
import re

from ollama_client import PROJECT_DIR, chat, prepare_ollama

REQUIREMENT_PATH = PROJECT_DIR / "input" / "requirement.md"
OUTPUT_PATH = PROJECT_DIR / "output" / "test_cases.json"
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

STRING_LIST = {"type": "array", "items": {"type": "string"}}
OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {"titles": STRING_LIST},
    "required": ["titles"],
}
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


def input_fields(requirement):
    fields = [name for name, rest in INPUT_FIELD.findall(requirement) if "чекбокс" not in rest.lower()]
    if not fields:
        raise ValueError("В требовании нет полей в формате «- **Имя.** ...»")
    return fields


def build_outline_prompt(requirement, count, existing):
    return f"""Ты senior QA-инженер.

Контекст (требование):
{requirement}

Техника: применяй классы эквивалентности и анализ граничных значений.
Включи позитивные, негативные и граничные проверки.

Формат: в поле titles верни ровно {count} разных коротких названий тест-кейсов.
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
- длинные значения не печатай целиком, пиши описанием: «строка из 51 символа»."""


def validate_outline(data, count):
    titles = [title.strip() for title in data["titles"] if title.strip()]
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


def suite_coverage(cases, requirement):
    required = {(field, check) for field in input_fields(requirement) for check in CHECKS}
    covered = {(case["field"], case["check"]) for case in cases}
    missing = sorted(required - covered)
    return {
        "required": len(required),
        "covered": len(required) - len(missing),
        "missing": [f"{field}: {check}" for field, check in missing],
    }


def generate_cases(requirement, free_count=6):
    plan = [
        (field, check, f"{field}: {description}")
        for field in input_fields(requirement)
        for check, description in CHECKS.items()
    ]
    outline = ask_valid(
        build_outline_prompt(requirement, free_count, [title for _, _, title in plan]),
        OUTLINE_SCHEMA,
        lambda data: validate_outline(data, free_count),
    )
    titles = list(dict.fromkeys(title.strip() for title in outline["titles"] if title.strip()))[:free_count]
    plan += [(None, None, title) for title in titles]

    cases = []
    for number, (field, check, title) in enumerate(plan, start=1):
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
        cases.append({"id": f"TC-{len(cases) + 1:03d}", "field": field, "check": check, **case})
    return cases


if __name__ == "__main__":
    prepare_ollama()
    requirement = REQUIREMENT_PATH.read_text(encoding="utf-8")
    cases = generate_cases(requirement)
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Сохранено кейсов: {len(cases)} → {OUTPUT_PATH}")
    print("Покрытие обязательных проверок:", suite_coverage(cases, requirement))
