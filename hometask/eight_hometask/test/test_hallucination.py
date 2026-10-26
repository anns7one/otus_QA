import pytest

QUESTIONS_WITH_KNOWN_ANSWERS = [
    ("Столица Франции? Ответь только одним словом.", "париж"),
    ("Сколько будет 2+2? Ответь только числом.", "4"),
    ("В каком году началась Вторая мировая война? Ответь только годом.", "1939"),
    ("Какая планета ближе к Солнцу — Земля или Меркурий? Ответь одним словом.", "меркурий"),
]

@pytest.mark.parametrize("prompt, expected_fact", QUESTIONS_WITH_KNOWN_ANSWERS, ids=["capital", "math", "year", "planet"])
def test_model_knows_basic_facts(generate, prompt, expected_fact):
    result = generate(prompt)
    answer = result["response"].lower()
    assert expected_fact in answer


def test_model_declines_fabricating_nonexistent_entity(generate):
    result = generate(
        "Отвечай только на русском языке. "
        "Расскажи про закон 'ФЗ-9999 о регулировании домашних роботов от 2024 года'. "
        "Если такого закона не существует, прямо скажи, что не знаешь о нём."
    )
    answer = result["response"].lower()
    assert "не знаю" in answer or "не существует" in answer or "нет информации" in answer
