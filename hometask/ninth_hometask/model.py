import joblib
from sklearn.linear_model import LogisticRegression

MODEL_PATH = "artifacts/model.joblib"


def train_model(X_train, y_train):
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_train, y_train)
    return model


def save_model(model, path=MODEL_PATH):
    joblib.dump(model, path)


def load_model(path=MODEL_PATH):
    return joblib.load(path)
