import json
import random

from generate_cases import CASE_SCHEMA, ask_valid, validate_case
from ollama_client import PROJECT_DIR, chat, ensure_model, prepare_ollama

DATA_DIR = PROJECT_DIR / "data"
TRAIN_REQUIREMENTS_PATH = DATA_DIR / "train_requirements.json"
TRAIN_SCENARIOS_PATH = DATA_DIR / "train_scenarios.jsonl"
GOLD_PATH = DATA_DIR / "gold.jsonl"
GOLD_GOOD, GOLD_PER_BAD, GOLD_SEED = 15, 5, 42
HUMAN_ANNOTATOR = "anna"
JUDGE_MODEL = "llama3.1:8b"
METRICS = ["readability", "goal_clarity", "coverage", "consistency"]
DOMAINS = [
    "регистрация с полями имя, e-mail, телефон и пароль",
    "регистрация только по e-mail и паролю",
    "регистрация с согласием с политикой конфиденциальности",
    "авторизация по e-mail и паролю",
    "авторизация по номеру телефона и паролю",
    "восстановление пароля по e-mail",
    "поле «Имя» в форме регистрации",
    "поле «E-mail» в форме регистрации",
    "поле «Телефон» с маской +7 в форме регистрации",
    "поле «Пароль» с требованиями к сложности",
    "проверка уникальности e-mail при регистрации",
    "сообщение «Заполните обязательные поля» в форме регистрации",
    "регистрация только по номеру телефона и паролю",
    "авторизация по e-mail или телефону в одном поле",
    "автоматическая авторизация сразу после регистрации",
    "восстановление пароля по номеру телефона",
    "ввод нового пароля после восстановления",
    "переход из формы регистрации к авторизации и восстановлению пароля",
    "проверка уникальности номера телефона при регистрации",
    "поп-ап подтверждения успешной регистрации",
    "чекбокс согласия с политикой конфиденциальности и кнопка «Зарегистрироваться»",
    "регистрация с именем кириллицей и латиницей",
    "форма авторизации с полями логин и пароль",
    "форма восстановления пароля с полем e-mail или телефон",
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
- fields: 1–4 поля ввода; name — название поля, rules — правила поля одной строкой:
  обязательно ли оно, длина «от N до M символов», допустимые символы, текст ошибки в кавычках «»;
- behavior: 2–3 пункта о том, что происходит при успехе и при ошибке."""


def render_requirement(number, data):
    lines = [f"# DS-{number:02d} - {data['title'].strip()}", "", data["purpose"].strip(), ""]
    lines += [f"- **{field['name'].strip().rstrip('.')}.** {field['rules'].strip()}" for field in data["fields"]]
    lines += ["", "## Поведение", ""] + [f"- {item.strip()}" for item in data["behavior"]]
    return "\n".join(lines) + "\n"


def validate_requirement(data):
    if not 1 <= len(data["fields"]) <= 4:
        raise ValueError(f"нужно 1–4 поля, получено {len(data['fields'])}")
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
    requirements = json.loads(TRAIN_REQUIREMENTS_PATH.read_text(encoding="utf-8")) if TRAIN_REQUIREMENTS_PATH.exists() else []
    for number, domain in enumerate(DOMAINS[len(requirements):], start=len(requirements) + 1):
        print(f"Требование {number}/{len(DOMAINS)}: {domain}")
        data = ask_valid(build_requirement_prompt(domain), REQUIREMENT_SCHEMA, validate_requirement, temperature=0.7)
        requirements.append({"id": f"DS-{number:02d}", "domain": domain, "text": render_requirement(number, data)})
        TRAIN_REQUIREMENTS_PATH.write_text(json.dumps(requirements, ensure_ascii=False, indent=2), encoding="utf-8")
    return requirements


def build_scenarios(requirements):
    scenarios = load_jsonl(TRAIN_SCENARIOS_PATH)
    done = {(item["requirement_id"], item["slot"]) for item in scenarios}
    with TRAIN_SCENARIOS_PATH.open("a", encoding="utf-8") as file:
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


RUBRIC = {
    "readability": ("Читаемость", "понятный язык, одно действие в шаге, нет двусмысленности"),
    "goal_clarity": ("Чёткость целей", "из названия и описания ясно, что и зачем проверяется"),
    "coverage": ("Покрытие", "учтены ограничения требования, есть граничные значения"),
    "consistency": ("Согласованность", "описание, шаги и ожидаемый результат не противоречат друг другу"),
}


def gold_sample(scenarios):
    rng = random.Random(GOLD_SEED)
    sample = rng.sample([item for item in scenarios if item["kind"] == "good"], GOLD_GOOD)
    for kind in sorted({item["kind"] for item in scenarios} - {"good"}):
        sample += rng.sample([item for item in scenarios if item["kind"] == kind], GOLD_PER_BAD)
    rng.shuffle(sample)
    return sample


def scenario_text(item, requirement):
    case = item["case"]
    lines = ["ТРЕБОВАНИЕ:", requirement, f"НАЗВАНИЕ: {case['title']}", f"ОПИСАНИЕ: {case['description']}", "ПРЕДУСЛОВИЯ:"]
    lines += [f"  - {step}" for step in case["preconditions"]]
    lines += ["ШАГИ:"] + [f"  {index}. {step}" for index, step in enumerate(case["steps"], start=1)]
    lines += [f"ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: {case['expected_result']}", "ГРАНИЧНЫЕ ЗНАЧЕНИЯ:"]
    lines += [f"  {value['value']!r} → {value['expected']}" for value in case["boundary_values"]]
    return "\n".join(lines)


def ask_labels(text):
    print(f"\n{'=' * 70}\n{text}\n\nОцени по 4 метрикам: 1 — хорошо, 0 — плохо.")
    for title, description in RUBRIC.values():
        print(f"  {title}: {description}")
    while True:
        answer = input("Четыре цифры в этом порядке, например 1101: ").strip()
        if len(answer) == len(METRICS) and set(answer) <= {"0", "1"}:
            return dict(zip(METRICS, map(int, answer)))
        print(f"Нужно ровно {len(METRICS)} цифры 0 или 1 без пробелов.")


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {metric: {"type": "integer", "enum": [0, 1]} for metric in METRICS},
    "required": METRICS,
}


def build_judge_prompt(text):
    rubric = "\n".join(f"- {metric}: {title} — {description}" for metric, (title, description) in RUBRIC.items())
    return f"""Ты senior QA-инженер, проверяешь качество тест-кейса по требованию.

{text}

Оцени тест-кейс по каждой метрике: 1 — хорошо, 0 — плохо.
{rubric}
Сверяй шаги и ожидаемый результат с правилами требования: если для недопустимого значения ожидается успех, согласованность — 0."""


def judge_labels(model):
    def labeler(text):
        return chat(build_judge_prompt(text), schema=JUDGE_SCHEMA, temperature=0, model=model)
    return labeler


def label_gold(annotator=HUMAN_ANNOTATOR, labeler=ask_labels):
    scenarios = load_jsonl(TRAIN_SCENARIOS_PATH)
    texts = {item["id"]: item["text"] for item in json.loads(TRAIN_REQUIREMENTS_PATH.read_text(encoding="utf-8"))}
    done = {(item["requirement_id"], item["slot"]) for item in load_jsonl(GOLD_PATH) if item["annotator"] == annotator}
    sample = gold_sample(scenarios)
    print(f"Разметчик {annotator}: {len(sample)} сценариев, уже размечено {len(done)}. Прервать можно в любой момент: Ctrl+C.")
    try:
        write_gold(sample, texts, done, annotator, labeler)
    except (KeyboardInterrupt, EOFError):
        print(f"\nРазметка прервана, ответы сохранены в {GOLD_PATH}. Повторный запуск продолжит с того же места.")
        return
    print(f"Готово: {GOLD_PATH}")


def judge_gold(model=JUDGE_MODEL):
    prepare_ollama()
    ensure_model(model)
    label_gold(model, judge_labels(model))


def write_gold(sample, texts, done, annotator, labeler):
    with GOLD_PATH.open("a", encoding="utf-8") as file:
        for number, item in enumerate(sample, start=1):
            if (item["requirement_id"], item["slot"]) in done:
                continue
            print(f"Сценарий {number}/{len(sample)} · проверяет требование {item['requirement_id']}")
            labels = labeler(scenario_text(item, texts[item["requirement_id"]]))
            row = {"requirement_id": item["requirement_id"], "slot": item["slot"], "annotator": annotator, "labels": labels}
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()


def main():
    DATA_DIR.mkdir(exist_ok=True)
    prepare_ollama()
    requirements = build_requirements()
    scenarios = build_scenarios(requirements)
    print(f"Требований: {len(requirements)}, сценариев: {len(scenarios)} → {TRAIN_SCENARIOS_PATH}")


if __name__ == "__main__":
    main()
