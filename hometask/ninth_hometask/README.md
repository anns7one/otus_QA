# ДЗ9. Автотесты ML-модели на scikit-learn с метриками и визуализацией

Система, которая генерирует датасет "прогоны автотестов" (синтетический,
через scikit-learn), обучает модель LogisticRegression предсказывать
падение теста, считает метрики качества (accuracy/precision/recall) и
визуализирует их. Отдельно созданы автотесты на pytest, проверяющие корректность загрузки данных, обучения модели, вычисления метрик и сохранения модели.

## Стек

Python 3, scikit-learn, pandas, numpy, seaborn, matplotlib, joblib, pytest.

## Структура

- `data.py` — генерация датасета (`make_classification`), train/test split, сохранение в CSV
- `model.py` — обучение LogisticRegression, сохранение/загрузка модели через joblib
- `metrics.py` — вычисление accuracy/precision/recall
- `visualize.py` — bar chart метрик
- `run.py` — точка входа: весь пайплайн целиком
- `data/test_runs.csv` — сохранённый датасет (создаётся при запуске `run.py`)
- `artifacts/model.joblib`, `artifacts/metrics.png` — результаты запуска
- `tests/` — автотесты: `test_data.py`, `test_model.py`, `test_metrics.py`, `test_persistence.py`
- `pytest.ini` — настройка `pythonpath`, чтобы тесты видели модули из корня проекта

## О датасете

Датасет синтетический (`sklearn.datasets.make_classification`), 600 строк,
10 признаков с условными "тестовыми" именами (`test_duration_ms`,
`assertions_count` и т.д.) — реальной связи с конкретными значениями тестов
нет, это сгенерированные данные с нужной статистической структурой (6
информативных признаков, 2 избыточных, 2 шумовых), подписанные под историю
про предсказание падения автотеста. Целевая переменная `test_failed` (0/1),
классы намеренно неравномерны (70%/30%).

## Локальный запуск

1. Установить зависимости:
   ```
   pip install -r requirements.txt
   ```
2. Обучить модель и получить метрики:
   ```
   python run.py
   ```
   Результат — `data/test_runs.csv`, `artifacts/model.joblib`, `artifacts/metrics.png`, метрики в консоли.
3. Прогнать автотесты:
   ```
   pytest -v
   ```

## Проверка

`pytest -v` — все тесты должны быть зелёными (11 штук: загрузка данных,
обучение модели, метрики, сохранение модели).
