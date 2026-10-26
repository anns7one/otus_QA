import difflib

CONSISTENCY_PROMPT = "Столица Франции? Ответь только одним словом."
REPEATS = 5
SIMILARITY_THRESHOLD = 0.8


def test_repeated_answers_are_consistent(generate):
    answers = [
        generate(CONSISTENCY_PROMPT, temperature=0.7)["response"].strip().lower()
        for _ in range(REPEATS)
    ]

    baseline = answers[0]
    for answer in answers[1:]:
        ratio = difflib.SequenceMatcher(None, baseline, answer).ratio()
        assert ratio >= SIMILARITY_THRESHOLD, (
            f"Ответы разошлись: '{baseline}' vs '{answer}' (ratio={ratio:.2f})"
        )
