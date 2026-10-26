from pathlib import Path

from data import load_dataset, split_dataset, save_dataset_csv
from model import train_model, save_model
from metrics import compute_metrics
from visualize import plot_metrics


def main():
    Path("data").mkdir(exist_ok=True)
    Path("artifacts").mkdir(exist_ok=True)

    X, y = load_dataset()
    save_dataset_csv(X, y)

    X_train, X_test, y_train, y_test = split_dataset(X, y)

    model = train_model(X_train, y_train)
    save_model(model)

    y_pred = model.predict(X_test)
    metrics = compute_metrics(y_test, y_pred)

    print("Метрики модели:")
    for name, value in metrics.items():
        print(f"  {name}: {value:.3f}")

    plot_metrics(metrics)
    print("Готово: artifacts/model.joblib, artifacts/metrics.png")


if __name__ == "__main__":
    main()
