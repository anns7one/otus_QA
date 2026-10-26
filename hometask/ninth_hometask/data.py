import pandas as pd
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split

RANDOM_STATE = 42
TEST_SIZE = 0.2

FEATURE_NAMES = [
    "test_duration_ms",        # сколько тест выполнялся, мс
    "assertions_count",        # сколько проверок (assert) в тесте
    "lines_changed",           # сколько строк кода изменено в PR
    "code_coverage_pct",       # покрытие кода, %
    "retries_last_10_runs",    # сколько раз тест перезапускали из последних 10 прогонов
    "flaky_history_score",     # оценка "нестабильности" теста по истории
    "dependencies_count",      # сколько внешних сервисов/зависимостей трогает тест
    "complexity_score",        # сложность тестируемого кода
    "parallel_workers",        # сколько воркеров выполняли тесты параллельно
    "queue_wait_ms",           # сколько тест ждал в очереди CI, мс
]


def load_dataset():
    X, y = make_classification(
        n_samples=600,
        n_features=10,
        n_informative=6,
        n_redundant=2,
        weights=[0.7, 0.3],
        random_state=RANDOM_STATE,
    )
    X = pd.DataFrame(X, columns=FEATURE_NAMES)
    y = pd.Series(y, name="test_failed")
    return X, y


def split_dataset(X, y):
    return train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )


def save_dataset_csv(X, y, path="data/test_runs.csv"):
    df = X.copy()
    df["test_failed"] = y
    df.to_csv(path, index=False)
