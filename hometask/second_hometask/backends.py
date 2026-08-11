"""Два бэкенда генерации с одним интерфейсом.

NgramBackend  — работает на обученной DocGeneratorLLM. Структуру документа даёт
                шаблон, формулировки достраивает модель. Связного текста от
                n-грамм ждать нельзя — это честное ограничение метода.
OllamaBackend — локальная LLM (llama3.2) через Ollama. Даёт связный текст.
                Промпт строится по схеме «Роль → Контекст → Задача → Формат».

Оба возвращают markdown и пишут одни и те же 4 документа.
"""

from __future__ import annotations

import re
import textwrap

from model import DocGeneratorLLM
from page_context import PAGE_URL, as_prompt_block

OLLAMA_MODEL = "llama3.2"

ROLE = (
    "Ты senior QA-инженер. Пишешь по существу, без воды. "
    "Пиши СТРОГО на русском языке кириллицей — латиница только в названиях "
    "статусов (PASSED/FAILED), идентификаторах (TC-001, BR-001) и URL. "
    "Никакой транслитерации русских слов латиницей."
)

# Строгие шаблоны вывода (few-shot): малая модель без образца теряет разделы
# и выдумывает содержимое. Шаблон — самый дешёвый способ стабилизировать формат.
TASKS = {
    "test-cases": (
        "Составь РОВНО 3 тест-кейса:\n"
        "  TC-001 — позитивный (основной сценарий)\n"
        "  TC-002 — позитивный (другое требование)\n"
        "  TC-003 — ОБЯЗАТЕЛЬНО негативный: пользователь делает что-то "
        "неверно или система в нештатном состоянии (например, комбинация "
        "фильтров без результатов, или обрыв сети при догрузке). "
        "В поле «Тип» у TC-003 напиши именно слово «негативный».\n"
        "Используй только элементы страницы из контекста и требования BR-xxx.\n"
        "Заполни шаблон для каждого кейса, ничего не пропуская:\n\n"
        "## TC-00N — <краткий заголовок>\n"
        "- Требование: BR-00N\n"
        "- Приоритет: Высокий | Средний | Низкий\n"
        "- Тип: позитивный | негативный\n"
        "- Предусловия: <что должно быть выполнено до старта>\n\n"
        "**Шаги:**\n"
        "1. <действие пользователя>\n"
        "2. <действие пользователя>\n"
        "3. <действие пользователя>\n\n"
        "**Ожидаемый результат:** <проверяемый результат, одно предложение>\n"
    ),
    "checklist": (
        "Составь чек-лист проверок страницы по шаблону:\n\n"
        "## <Раздел>\n"
        "- [ ] <одна короткая проверяемая формулировка>\n\n"
        "Разделы строго такие: Загрузка страницы, Фильтры, Карточки курсов, "
        "Пагинация, Адаптивность. В каждом разделе 3-5 пунктов."
    ),
    "test-plan": (
        "Составь тест-план по ISO 29119-3, заполнив шаблон:\n\n"
        "## Объём\n<что именно тестируем, списком>\n\n"
        "## Вне объёма\n<что сознательно НЕ тестируем, списком>\n\n"
        "## Подход\n<уровни и виды тестирования>\n\n"
        "## Критерии входа\n<условия старта, списком>\n\n"
        "## Критерии выхода\n<измеримые условия завершения, списком>\n\n"
        "## Риски\n| Риск | Мера снижения |\n|---|---|\n<строки таблицы>\n\n"
        "## Ресурсы\n<кто и на каком окружении тестирует>\n"
    ),
    # Фактическую часть отчёта (сводка, таблица результатов, дефекты, покрытие)
    # рендерит КОД из results.json — модель физически не может исказить цифры.
    # Модели остаются только два интерпретирующих раздела.
    "test-report": (
        "Напиши ДВА раздела отчёта о тестировании — и больше ничего.\n"
        "Опирайся только на «Факты прогона» ниже, не придумывай проверки.\n\n"
        "## Оценка остаточного риска\n"
        "<Что осталось непроверенным или под риском и чем это грозит бизнесу. "
        "НЕ повторяй цифры сводки — они уже есть выше в отчёте. 2-4 предложения.>\n\n"
        "## Вывод о релизе\n"
        "<Одна из формулировок: «релиз разрешён», «релиз с оговорками», "
        "«релиз не рекомендуется» — и обоснование. Учти: если есть незакрытый "
        "дефект severity Major или выше, релиз без оговорок невозможен. "
        "2-3 предложения.>\n"
    ),
}


class Backend:
    """Общий интерфейс: получить markdown-тело документа."""

    name = "base"

    def render(self, doc_type: str, extra_context: str = "") -> str:
        raise NotImplementedError


class OllamaBackend(Backend):
    name = "ollama"

    def __init__(self, model: str = OLLAMA_MODEL) -> None:
        import ollama  # импорт здесь, чтобы ngram-режим работал без пакета

        self._ollama = ollama
        self.model = model

    @staticmethod
    def is_available(model: str = OLLAMA_MODEL) -> bool:
        try:
            import ollama

            names = [m.get("model", "") for m in ollama.list().get("models", [])]
            return any(n.split(":")[0] == model.split(":")[0] for n in names)
        except Exception:
            return False

    def build_prompt(self, doc_type: str, extra_context: str = "") -> str:
        return "\n\n".join(
            [
                f"Роль: {ROLE}",
                f"Контекст — тестируемая страница:\n{as_prompt_block()}",
                extra_context.strip(),
                f"Задача: {TASKS[doc_type]}",
                "Формат: markdown, на русском языке. Только сам документ, "
                "без вступлений вроде «Вот ваш документ».",
            ]
        ).strip()

    def render(self, doc_type: str, extra_context: str = "") -> str:
        response = self._ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": self.build_prompt(doc_type, extra_context)}],
            options={"temperature": 0.1},  # документация, а не творчество
        )
        return response["message"]["content"].strip()


class NgramBackend(Backend):
    """Fallback: структура из шаблона + формулировки от обученной n-gram модели."""

    name = "ngram"

    def __init__(self, model: DocGeneratorLLM) -> None:
        self.model = model

    def _phrase(self, seed: str, length: int = 8) -> str:
        """Достроить фразу обученной моделью."""
        generated = self.model.generate(seed, length=length)
        return generated[0].upper() + generated[1:] if generated else seed

    def render(self, doc_type: str, extra_context: str = "") -> str:
        note = (
            "> Сгенерировано n-gram моделью (биграммы/триграммы). Модель обучена\n"
            "> на предметном корпусе и достраивает формулировки, но связного текста\n"
            "> статистика частот дать не может — структуру задаёт шаблон.\n"
            "> Для связного текста запустите с `--backend ollama`.\n"
        )
        builder = {
            "test-cases": self._test_cases,
            "checklist": self._checklist,
            "test-plan": self._test_plan,
            "test-report": self._test_report,
        }[doc_type]
        return note + "\n" + builder(extra_context)

    def _test_cases(self, extra: str) -> str:
        cases = [
            ("TC-001", "BR-001", "Высокий", "позитивный", "открыть страницу", "проверить что"),
            ("TC-002", "BR-003", "Средний", "позитивный", "нажать кнопку", "проверить что"),
            ("TC-003", "BR-002", "Высокий", "негативный", "выбрать фильтр", "ожидаемый результат"),
        ]
        out = [f"# Тест-кейсы: каталог курсов\n\nURL: {PAGE_URL}\n"]
        for tc_id, br, prio, kind, step_seed, exp_seed in cases:
            out.append(
                textwrap.dedent(
                    f"""
                    ## {tc_id} — {self._phrase(step_seed, 6)}

                    - Требование: {br}
                    - Приоритет: {prio}
                    - Тип: {kind}

                    **Шаги:**
                    1. {self._phrase(step_seed, 6)}
                    2. {self._phrase("нажать кнопку", 5)}

                    **Ожидаемый результат:** {self._phrase(exp_seed, 8)}
                    """
                ).strip()
                + "\n"
            )
        return "\n".join(out)

    def _checklist(self, extra: str) -> str:
        seeds = [
            "страница открывается", "фильтр направление", "фильтр уровень",
            "кнопка очистить", "кнопка показать", "карточка курса",
            "блок рекомендаций", "вёрстка не", "заголовок страницы",
        ]
        items = "\n".join(f"- [ ] {self._phrase(s, 6)}" for s in seeds)
        return f"# Чек-лист: каталог курсов\n\nURL: {PAGE_URL}\n\n{items}\n"

    def _test_plan(self, extra: str) -> str:
        sections = {
            "Объём": "объём тестирования включает",
            "Вне объёма": "вне объёма тестирования",
            "Подход": "подход функциональное",
            "Критерии входа": "критерий входа",
            "Критерии выхода": "критерий выхода",
            "Риски": "риск блок",
        }
        body = "\n".join(
            f"## {title}\n\n{self._phrase(seed, 8)}\n" for title, seed in sections.items()
        )
        return f"# Тест-план: каталог курсов\n\nURL: {PAGE_URL}\n\n{body}"

    def _test_report(self, extra: str) -> str:
        """Только интерпретирующие разделы — факты подставит generate.py.

        Вердикт берём из контекста: его решил код по порогам, n-gram модель
        не имеет права его переформулировать.
        """
        match = re.search(r"ВЕРДИКТ \(решён по правилам, НЕ меняй его\): (.+)", extra)
        verdict = match.group(1).strip() if match else "требуется ручная оценка"
        reason = re.search(r"Основание: (.+)", extra)
        reason_text = reason.group(1).strip() if reason else ""
        return (
            "## Оценка остаточного риска\n\n"
            f"{self._phrase('риск блок', 8)}\n\n"
            "## Вывод о релизе\n\n"
            f"{verdict.capitalize()}"
            + (f" — {reason_text}." if reason_text else ".")
            + "\n"
        )
