import json

from generate_cases import CASE_SCHEMA, ask_valid, validate_case
from ollama_client import PROJECT_DIR, prepare_ollama

DATA_DIR = PROJECT_DIR / "data"
REQUIREMENTS_PATH = DATA_DIR / "requirements.json"
SCENARIOS_PATH = DATA_DIR / "scenarios.jsonl"
METRICS = ["readability", "goal_clarity", "coverage", "consistency"]
DOMAINS = [
    "вход в личный кабинет", "оформление заказа", "загрузка аватара", "бронирование номера в отеле",
    "перевод денег между счетами", "поиск авиабилетов", "регистрация на мероприятие", "смена пароля",
    "форма обратной связи", "добавление товара в корзину", "фильтр каталога по цене", "отзыв о товаре",
    "подписка на рассылку", "заявка на кредит", "запись к врачу", "восстановление пароля",
    "редактирование профиля", "применение промокода", "адрес доставки", "создание задачи в трекере",
    "оплата картой", "приглашение пользователя в команду", "загрузка документа", "настройка уведомлений",
]
DEFECTS = {
    "readability": "шаги написаны путано: длинные запутанные предложения, канцелярит, несколько действий в одном шаге, неоднозначные слова",
    "goal_clarity": "название и описание размытые: непонятно, что именно и зачем проверяет тест",
    "coverage": "тест игнорирует ограничения требования: нет граничных значений, проверяются только обычные данные",
    "consistency": "ожидаемый результат противоречит шагам или описанию: например, вводится недопустимое значение, а ожидается успех",
}
PLAN = (
    [("good", [1, 1, 1, 1])] * 3
    + [(f"bad_{metric}", [0 if m == metric else 1 for m in METRICS]) for metric in METRICS]
    + [("bad_all", [0, 0, 0, 0])]
)
REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "purpose": {"type": "string"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "rules": {"type": "string"}},
                "required": ["name", "rules"],
            },
        },
        "behavior": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "purpose", "fields", "behavior"],
}


def build_requirement_prompt(domain):
    return f"""Ты аналитик. Опиши требование к функции «{domain}» на русском языке.

- title: короткое название функции;
- purpose: одно предложение о назначении;
- fields: 2–4 поля ввода; name — название поля, rules — правила поля одной строкой:
  обязательно ли оно, длина «от N до M символов», допустимые символы, текст ошибки в кавычках «»;
- behavior: 2–3 пункта о том, что происходит при успехе и при ошибке."""


def render_requirement(number, data):
    lines = [f"# DS-{number:02d} - {data['title'].strip()}", "", data["purpose"].strip(), ""]
    lines += [f"- **{field['name'].strip().rstrip('.')}.** {field['rules'].strip()}" for field in data["fields"]]
    lines += ["", "## Поведение", ""] + [f"- {item.strip()}" for item in data["behavior"]]
    return "\n".join(lines) + "\n"


def validate_requirement(data):
    if not 2 <= len(data["fields"]) <= 4:
        raise ValueError(f"нужно 2–4 поля, получено {len(data['fields'])}")
    if not any(char.isdigit() for field in data["fields"] for char in field["rules"]):
        raise ValueError("нет числовых ограничений")
    if not data["behavior"]:
        raise ValueError("нет пунктов поведения")


def build_scenario_prompt(requirement, kind, existing):
    if kind == "good":
        task = "Напиши качественный тест-кейс: понятные шаги, ясная цель, граничные значения из требования, ожидаемый результат согласован с шагами."
    elif kind == "bad_all":
        task = "Напиши плохой тест-кейс сразу со всеми недостатками:\n- " + "\n- ".join(DEFECTS.values())
    else:
        task = f"Напиши тест-кейс с одним недостатком: {DEFECTS[kind.removeprefix('bad_')]}. Всё остальное сделай качественно."
    return f"""Ты senior QA-инженер, готовишь обучающие примеры.

Требование:
{requirement}

Задача: {task}
Проверяй правило требования, которого ещё нет в списке ниже.
Объём текста делай обычным, как у качественного тест-кейса, не короче.

Уже есть тест-кейсы:
{chr(10).join(existing) or "нет"}

Поля: title, description, preconditions, steps, expected_result, boundary_values (value — вводимое значение, expected — результат).
Пиши только на русском языке."""


def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_requirements():
    requirements = json.loads(REQUIREMENTS_PATH.read_text(encoding="utf-8")) if REQUIREMENTS_PATH.exists() else []
    for number, domain in enumerate(DOMAINS[len(requirements):], start=len(requirements) + 1):
        print(f"Требование {number}/{len(DOMAINS)}: {domain}")
        data = ask_valid(build_requirement_prompt(domain), REQUIREMENT_SCHEMA, validate_requirement, temperature=0.7)
        requirements.append({"id": f"DS-{number:02d}", "domain": domain, "text": render_requirement(number, data)})
        REQUIREMENTS_PATH.write_text(json.dumps(requirements, ensure_ascii=False, indent=2), encoding="utf-8")
    return requirements


def build_scenarios(requirements):
    scenarios = load_jsonl(SCENARIOS_PATH)
    done = {(item["requirement_id"], item["slot"]) for item in scenarios}
    with SCENARIOS_PATH.open("a", encoding="utf-8") as file:
        for requirement in requirements:
            titles = [item["case"]["title"] for item in scenarios if item["requirement_id"] == requirement["id"]]
            for slot, (kind, labels) in enumerate(PLAN):
                if (requirement["id"], slot) in done:
                    continue
                print(f"{requirement['id']} [{slot + 1}/{len(PLAN)}] {kind}")
                try:
                    case = ask_valid(
                        build_scenario_prompt(requirement["text"], kind, titles),
                        CASE_SCHEMA,
                        validate_case,
                        temperature=0.7,
                    )
                except RuntimeError as error:
                    print(f"  пропущен: {error}")
                    continue
                if case["title"] in titles:
                    print("  пропущен: дубль названия")
                    continue
                titles.append(case["title"])
                item = {"requirement_id": requirement["id"], "slot": slot, "kind": kind,
                        "labels": dict(zip(METRICS, labels)), "case": case}
                scenarios.append(item)
                file.write(json.dumps(item, ensure_ascii=False) + "\n")
                file.flush()
    return scenarios


def main():
    DATA_DIR.mkdir(exist_ok=True)
    prepare_ollama()
    requirements = build_requirements()
    scenarios = build_scenarios(requirements)
    print(f"Требований: {len(requirements)}, сценариев: {len(scenarios)} → {SCENARIOS_PATH}")


if __name__ == "__main__":
    main()
