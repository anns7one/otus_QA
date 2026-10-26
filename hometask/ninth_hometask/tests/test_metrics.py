from metrics import compute_metrics


def test_metrics_on_known_values():
    y_true = [1, 0, 1, 0, 1]
    y_pred = [1, 0, 0, 0, 1]

    result = compute_metrics(y_true, y_pred)

    assert result["accuracy"] == 4 / 5
    assert result["precision"] == 2 / 2
    assert result["recall"] == 2 / 3


def test_metrics_are_within_valid_range(trained_model, dataset_split):
    _, X_test, _, y_test = dataset_split
    y_pred = trained_model.predict(X_test)
    result = compute_metrics(y_test, y_pred)

    for value in result.values():
        assert 0.0 <= value <= 1.0
