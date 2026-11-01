import json
import re

from ollama_client import PROJECT_DIR, chat, prepare_ollama

REQUIREMENT_PATH = PROJECT_DIR / "input" / "requirement.md"
OUTPUT_PATH = PROJECT_DIR / "output" / "test_cases.json"
MAX_ATTEMPTS = 3
BASE_SEED = 42
TEXT_FIELDS = ["title", "description", "expected_result"]
LIST_FIELDS = ["preconditions", "steps", "boundary_values"]
FOREIGN_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
QUOTED = re.compile(r"[«'\"“]([^«»'\"“”]{3,})[»'\"”]")
PLACEHOLDER = "[текст не указан в требовании]"

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
        "boundary_values": STRING_LIST,
    },
    "required": TEXT_FIELDS + LIST_FIELDS,
}


def build_outline_prompt(requirement, count):
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
- boundary_values: только значения того поля, которое проверяет этот тест, и поведение на каждом.

Как записывать boundary_values при числовом диапазоне: значение на единицу меньше минимума, минимум, максимум, значение на единицу больше максимума.
Пример для другого поля «Возраст» с диапазоном от 18 до 65: "17 — ошибка", "18 — принимается", "65 — принимается", "66 — ошибка".
Если числовых границ нет, укажи пограничные случаи этого поля: пустое значение, неверный формат.

Ограничения:
- пиши только на русском языке;
- не придумывай правил, которых нет в требовании;
- текст сообщения в кавычках пиши только дословно из требования; если в требовании текста нет, пиши «появляется сообщение об ошибке» без кавычек и без своего текста;
- длинные значения не печатай целиком, пиши описанием: «строка из 51 символа»."""


def validate_outline(data, count):
    titles = [title.strip() for title in data["titles"] if title.strip()]
    if len(set(titles)) < count:
        raise ValueError(f"нужно {count} разных названий, получено {len(set(titles))}")


def validate_case(case):
    for field in TEXT_FIELDS:
        if not case[field].strip():
            raise ValueError(f"пустое поле {field}")
    for field in LIST_FIELDS:
        if not case[field] or not all(item.strip() for item in case[field]):
            raise ValueError(f"пустой список или элемент в поле {field}")
    if FOREIGN_CHARS.search(json.dumps(case, ensure_ascii=False)):
        raise ValueError("в тексте есть символы другого языка")


def ask_valid(prompt, schema, validate, temperature=0.2):
    for attempt in range(MAX_ATTEMPTS):
        try:
            data = chat(prompt, schema=schema, temperature=temperature, seed=BASE_SEED + attempt)
            validate(data)
            return data
        except (ValueError, KeyError) as error:
            print(f"  попытка {attempt + 1}/{MAX_ATTEMPTS} не прошла: {error}")
    raise RuntimeError(f"Модель не дала корректный ответ за {MAX_ATTEMPTS} попытки")


def generate_cases(requirement, count=10):
    outline = ask_valid(
        build_outline_prompt(requirement, count),
        OUTLINE_SCHEMA,
        lambda data: validate_outline(data, count),
    )
    titles = list(dict.fromkeys(title.strip() for title in outline["titles"] if title.strip()))[:count]

    cases = []
    for number, title in enumerate(titles, start=1):
        print(f"[{number}/{count}] {title}")
        case = ask_valid(build_case_prompt(requirement, title), CASE_SCHEMA, validate_case)
        cases.append({"id": f"TC-{number:03d}", **case})
    return cases


if __name__ == "__main__":
    prepare_ollama()
    requirement = REQUIREMENT_PATH.read_text(encoding="utf-8")
    cases = generate_cases(requirement)
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Сохранено кейсов: {len(cases)} → {OUTPUT_PATH}")
