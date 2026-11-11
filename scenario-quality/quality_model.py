import json
import random

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from torch import nn

from build_dataset import METRICS, REQUIREMENTS_PATH, SCENARIOS_PATH, load_jsonl
from ollama_client import PROJECT_DIR

ENCODER_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_PATH = PROJECT_DIR / "output" / "model.pt"
TRAINING_PATH = PROJECT_DIR / "output" / "training_metrics.json"
SEED = 42
SPLIT = (0.7, 0.15)
THRESHOLDS = np.arange(0.05, 0.96, 0.05)
MAX_EPOCHS = 300
PATIENCE = 30

_encoder = None


def encoder():
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer(ENCODER_NAME)
    return _encoder


def case_parts(case):
    return [
        f"{case['title']}. {case['description']}",
        " ".join(case["steps"]),
        case["expected_result"],
        " ".join(f"{item['value']} → {item['expected']}" for item in case["boundary_values"]),
    ]


def features(cases, requirements):
    parts = [case_parts(case) for case in cases]
    flat = [text for item in parts for text in item] + list(requirements)
    vectors = encoder().encode(flat, normalize_embeddings=True, convert_to_numpy=True)
    count = len(case_parts(cases[0]))
    case_vectors = vectors[: len(cases) * count].reshape(len(cases), count, -1)
    requirement_vectors = vectors[len(cases) * count:]
    rows = []
    for parts_vec, requirement_vec in zip(case_vectors, requirement_vectors):
        similarities = [float(a @ b) for i, a in enumerate(parts_vec) for b in parts_vec[i + 1:]]
        similarities += [float(part @ requirement_vec) for part in parts_vec]
        rows.append(np.concatenate([parts_vec.ravel(), similarities]))
    return torch.tensor(np.array(rows), dtype=torch.float32)


def text_length(case):
    return len(" ".join(case_parts(case)))


class QualityNet(nn.Module):
    def __init__(self, size):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(size, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, len(METRICS)))

    def forward(self, x):
        return self.layers(x)


def split_by_requirement(scenarios):
    ids = sorted({item["requirement_id"] for item in scenarios})
    random.Random(SEED).shuffle(ids)
    train_end = round(len(ids) * SPLIT[0])
    val_end = train_end + round(len(ids) * SPLIT[1])
    groups = {"train": set(ids[:train_end]), "val": set(ids[train_end:val_end]), "test": set(ids[val_end:])}
    return {name: [item for item in scenarios if item["requirement_id"] in group] for name, group in groups.items()}


def dataset(items, requirement_texts):
    x = features([item["case"] for item in items], [requirement_texts[item["requirement_id"]] for item in items])
    y = torch.tensor([[item["labels"][metric] for metric in METRICS] for item in items], dtype=torch.float32)
    return x, y


def train_net(x_train, y_train, x_val, y_val):
    torch.manual_seed(SEED)
    net = QualityNet(x_train.shape[1])
    optimizer = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
    positive = y_train.mean(dim=0).clamp(0.01, 0.99)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=(1 - positive) / positive)
    history, best, best_state, waited = [], float("inf"), None, 0
    for epoch in range(1, MAX_EPOCHS + 1):
        net.train()
        optimizer.zero_grad()
        loss = loss_fn(net(x_train), y_train)
        loss.backward()
        optimizer.step()
        net.eval()
        with torch.no_grad():
            val_loss = loss_fn(net(x_val), y_val).item()
        history.append({"epoch": epoch, "train_loss": loss.item(), "val_loss": val_loss})
        if val_loss < best:
            best, best_state, waited = val_loss, {k: v.clone() for k, v in net.state_dict().items()}, 0
        else:
            waited += 1
            if waited >= PATIENCE:
                break
    net.load_state_dict(best_state)
    print(f"Обучение остановлено на эпохе {len(history)}, лучшая val loss {best:.3f}")
    return net, history


def scores(y_true, probabilities, threshold):
    result = {}
    for index, metric in enumerate(METRICS):
        truth, prob = y_true[:, index], probabilities[:, index]
        auc = roc_auc_score(truth, prob) if len(set(truth)) > 1 else None
        result[metric] = {"macro_f1": f1_score(truth, prob >= threshold, average="macro", zero_division=0), "roc_auc": auc}
    return result


def choose_threshold(y_val, probabilities):
    def quality(threshold):
        return np.mean([f1_score(y_val[:, i], probabilities[:, i] >= threshold, average="macro", zero_division=0)
                        for i in range(len(METRICS))])
    return float(max(THRESHOLDS, key=quality))


def baselines(train, test, y_train, y_test, threshold):
    majority = np.tile(y_train.numpy().mean(axis=0), (len(test), 1))
    length_train = np.array([[text_length(item["case"])] for item in train])
    length_test = np.array([[text_length(item["case"])] for item in test])
    by_length = np.column_stack([
        LogisticRegression().fit(length_train, y_train[:, i]).predict_proba(length_test)[:, 1]
        if len(set(y_train[:, i].tolist())) > 1 else majority[:, i]
        for i in range(len(METRICS))
    ])
    return {
        "majority": scores(y_test.numpy(), majority, threshold),
        "length_only": scores(y_test.numpy(), by_length, threshold),
    }


def train():
    scenarios = load_jsonl(SCENARIOS_PATH)
    requirement_texts = {item["id"]: item["text"] for item in json.loads(REQUIREMENTS_PATH.read_text(encoding="utf-8"))}
    parts = split_by_requirement(scenarios)
    print({name: len(items) for name, items in parts.items()})
    x_train, y_train = dataset(parts["train"], requirement_texts)
    x_val, y_val = dataset(parts["val"], requirement_texts)
    x_test, y_test = dataset(parts["test"], requirement_texts)
    net, history = train_net(x_train, y_train, x_val, y_val)
    with torch.no_grad():
        threshold = choose_threshold(y_val.numpy(), torch.sigmoid(net(x_val)).numpy())
        probabilities = torch.sigmoid(net(x_test)).numpy()
    print(f"Порог, подобранный на validation: {threshold:.2f}")
    report = {
        "split": {name: sorted({item["requirement_id"] for item in items}) for name, items in parts.items()},
        "threshold": threshold,
        "history": history,
        "test": {
            "model": scores(y_test.numpy(), probabilities, threshold),
            **baselines(parts["train"], parts["test"], y_train, y_test, threshold),
        },
    }
    MODEL_PATH.parent.mkdir(exist_ok=True)
    torch.save({"state": net.state_dict(), "size": x_train.shape[1], "threshold": threshold}, MODEL_PATH)
    TRAINING_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, result in report["test"].items():
        print(name, {metric: (round(value["roc_auc"], 2), round(value["macro_f1"], 2)) for metric, value in result.items()})
    return net, report


def load_net():
    saved = torch.load(MODEL_PATH)
    net = QualityNet(saved["size"])
    net.load_state_dict(saved["state"])
    net.eval()
    return net


def predict(net, cases, requirement):
    with torch.no_grad():
        probabilities = torch.sigmoid(net(features(cases, [requirement] * len(cases)))).numpy()
    return [dict(zip(METRICS, map(float, row))) for row in probabilities]


if __name__ == "__main__":
    train()
