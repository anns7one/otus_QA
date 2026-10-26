import pytest

from data import load_dataset, split_dataset
from model import train_model


@pytest.fixture(scope="session")
def dataset_split():
    X, y = load_dataset()
    return split_dataset(X, y)


@pytest.fixture(scope="session")
def trained_model(dataset_split):
    X_train, X_test, y_train, y_test = dataset_split
    return train_model(X_train, y_train)
