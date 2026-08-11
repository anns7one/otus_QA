"""Модель ДЗ-2: развитие биграммной TestLLM из первого домашнего задания.

TestLLM (из ДЗ-1) считает частоты пар «слово → следующее слово».
DocGeneratorLLM расширяет её тремя вещами:
  1. настраиваемый порядок n-грамм (bigram/trigram);
  2. generate() — цепочка предсказаний, а не одно слово;
  3. stats() — что модель выучила после train().
"""

from collections import defaultdict


class TestLLM:
    """Модель из первого ДЗ — без изменений, как основа."""

    def __init__(self) -> None:
        self.ngram_counts: defaultdict[str, defaultdict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.train_data: list[str] = []

    def train(self, data: list[str]) -> None:
        self.train_data = data
        for sentence in data:
            words = sentence.split()
            for i in range(len(words) - 1):
                current_word = words[i]
                next_word = words[i + 1]
                self.ngram_counts[current_word][next_word] += 1

    def predict_next_word(self, start_word: str) -> str:
        if start_word not in self.ngram_counts:
            return "Слово не найдено в обучающей выборке."
        next_words: defaultdict[str, int] = self.ngram_counts[start_word]
        if not next_words:
            return "Нет данных для предсказания."
        return max(next_words, key=next_words.get)


class DocGeneratorLLM(TestLLM):
    """Доработанная модель: n-граммы произвольного порядка + генерация текста."""

    def __init__(self, order: int = 2) -> None:
        super().__init__()
        if order < 2:
            raise ValueError("order должен быть >= 2 (минимум биграммы)")
        self.order = order

    def train(self, data: list[str]) -> None:
        """Обучение: считаем, какое слово следует за контекстом из order-1 слов.

        При order=2 поведение совпадает с моделью из ДЗ-1.
        """
        self.train_data = data
        context_len = self.order - 1
        for sentence in data:
            words = sentence.split()
            for i in range(len(words) - context_len):
                context = " ".join(words[i : i + context_len])
                next_word = words[i + context_len]
                self.ngram_counts[context][next_word] += 1

    def generate(self, seed: str, length: int = 20) -> str:
        """Генерирует цепочку слов, каждый раз беря самое частое продолжение."""
        context_len = self.order - 1
        words = seed.split()
        if len(words) < context_len:
            return seed
        for _ in range(length):
            context = " ".join(words[-context_len:])
            if context not in self.ngram_counts:
                break
            candidates = self.ngram_counts[context]
            if not candidates:
                break
            words.append(max(candidates, key=candidates.get))
        return " ".join(words)

    def stats(self) -> dict[str, int]:
        """Что модель выучила — доказательство того, что обучение произошло."""
        vocabulary = set(self.ngram_counts)
        for followers in self.ngram_counts.values():
            vocabulary.update(followers)
        return {
            "предложений в обучающей выборке": len(self.train_data),
            "уникальных контекстов": len(self.ngram_counts),
            "размер словаря": len(vocabulary),
            "всего переходов": sum(
                sum(f.values()) for f in self.ngram_counts.values()
            ),
        }


def _demo() -> None:
    """Самопроверка: модель обучается и предсказывает ожидаемое слово."""
    data = [
        "кот спит на диване",
        "кот ест рыбу",
        "кот спит на окне",
        "кот спит в коробке",
    ]

    bigram = DocGeneratorLLM(order=2)
    bigram.train(data)
    assert bigram.predict_next_word("кот") == "спит", "самое частое после 'кот' — 'спит'"
    assert bigram.stats()["предложений в обучающей выборке"] == 4

    trigram = DocGeneratorLLM(order=3)
    trigram.train(data)
    assert trigram.predict_next_word("кот спит") == "на", "после 'кот спит' чаще идёт 'на'"

    assert bigram.generate("кот", length=3).startswith("кот спит на"), "генерация цепочки"

    print("model.py: самопроверка пройдена")


if __name__ == "__main__":
    _demo()
