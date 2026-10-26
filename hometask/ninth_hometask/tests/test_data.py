from data import load_dataset


def test_dataset_has_expected_shape():
    X, y = load_dataset()
    assert X.shape[0] == 600
    assert X.shape[1] == 10
    assert len(y) == 600


def test_target_is_binary():
    _, y = load_dataset()
    assert set(y.unique()) == {0, 1}


def test_split_preserves_total_size(dataset_split):
    X_train, X_test, y_train, y_test = dataset_split
    assert len(X_train) + len(X_test) == 600
    assert len(y_train) + len(y_test) == 600


def test_split_has_no_missing_values(dataset_split):
    X_train, X_test, y_train, y_test = dataset_split
    assert not X_train.isnull().values.any()
    assert not X_test.isnull().values.any()
