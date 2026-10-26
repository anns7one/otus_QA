from sklearn.utils.validation import check_is_fitted


def test_model_is_fitted(trained_model):
    check_is_fitted(trained_model)


def test_predictions_shape_matches_test_set(trained_model, dataset_split):
    _, X_test, _, y_test = dataset_split
    predictions = trained_model.predict(X_test)
    assert len(predictions) == len(y_test)


def test_predictions_are_binary(trained_model, dataset_split):
    _, X_test, _, _ = dataset_split
    predictions = trained_model.predict(X_test)
    assert set(predictions).issubset({0, 1})
