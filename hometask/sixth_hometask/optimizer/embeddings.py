"""Эмбеддинги для похожести тестов и требований по смыслу (шаг 5, шаг 6 fallback).

Модель многоязычная: docstring'и в наших тестах русские и английские вперемешку.
Загружаем лениво (в конструкторе), а не при импорте модуля — импорт optimizer
не должен требовать 2 ГБ зависимостей, если человек хочет только --no-llm режим.
"""

_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder:
    def __init__(self, model_name: str = _MODEL_NAME):
        from sentence_transformers import SentenceTransformer, util
        self._util = util
        self._model = SentenceTransformer(model_name)

    def similarity(self, text_a: str, text_b: str) -> float:
        vectors = self._model.encode([text_a, text_b], convert_to_tensor=True)
        return float(self._util.cos_sim(vectors[0], vectors[1]).item())

    def pairwise_similarity(self, texts: list[str]):
        """Эмбеддит список текстов один раз и возвращает полную матрицу
        cosine similarity (matrix[i][j]) — дешевле, чем кодировать те же
        тексты заново на каждую пару при сравнении внутри бакета."""
        vectors = self._model.encode(texts, convert_to_tensor=True)
        return self._util.cos_sim(vectors, vectors)
