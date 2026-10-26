from model import save_model, load_model


def test_model_is_saved_to_disk(trained_model, tmp_path):
    path = tmp_path / "model.joblib"
    save_model(trained_model, path=str(path))
    assert path.exists()


def test_loaded_model_predicts_same_as_original(trained_model, dataset_split, tmp_path):
    _, X_test, _, _ = dataset_split
    path = tmp_path / "model.joblib"
    save_model(trained_model, path=str(path))

    loaded_model = load_model(path=str(path))

    original_predictions = trained_model.predict(X_test)
    loaded_predictions = loaded_model.predict(X_test)

    assert list(original_predictions) == list(loaded_predictions)
