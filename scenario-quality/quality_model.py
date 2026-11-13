import json
import random

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score, f1_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from torch import nn

from build_dataset import GOLD_PATH, METRICS, TRAIN_REQUIREMENTS_PATH, TRAIN_SCENARIOS_PATH, load_jsonl
from ollama_client import PROJECT_DIR

ENCODER_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_PATH = PROJECT_DIR / "output" / "model.pt"
TRAINING_PATH = PROJECT_DIR / "output" / "training_metrics.json"
SEED = 42
SPLIT = (0.7, 0.15)
THRESHOLDS = np.arange(0.05, 0.96, 0.05)
MAX_EPOCHS = 300
PATIENCE = 30
CV_FOLDS = 5

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


def fit_and_score(x, y, scenarios, fit, val, test):
    net, history = train_net(x[fit], y[fit], x[val], y[val])
    with torch.no_grad():
        threshold = choose_threshold(y[val].numpy(), torch.sigmoid(net(x[val])).numpy())
        probabilities = torch.sigmoid(net(x[test])).numpy()
    result = {
        "model": scores(y[test].numpy(), probabilities, threshold),
        **baselines([scenarios[i] for i in fit], [scenarios[i] for i in test], y[fit], y[test], threshold),
    }
    return net, history, threshold, result, probabilities


def cross_validate(x, y, scenarios, folds=CV_FOLDS):
    groups = [item["requirement_id"] for item in scenarios]
    runs = []
    out_of_fold = np.zeros((len(scenarios), len(METRICS)))
    for fold, (train_index, test_index) in enumerate(GroupKFold(n_splits=folds).split(x, groups=groups), start=1):
        train_ids = sorted({groups[i] for i in train_index})
        random.Random(SEED + fold).shuffle(train_ids)
        val_ids = set(train_ids[:max(1, round(len(train_ids) * SPLIT[1]))])
        fit = [i for i in train_index if groups[i] not in val_ids]
        val = [i for i in train_index if groups[i] in val_ids]
        *_, result, probabilities = fit_and_score(x, y, scenarios, fit, val, list(test_index))
        runs.append(result)
        out_of_fold[test_index] = probabilities
    summary = {}
    for name in runs[0]:
        summary[name] = {}
        for metric in METRICS:
            aucs = [run[name][metric]["roc_auc"] for run in runs if run[name][metric]["roc_auc"] is not None]
            f1s = [run[name][metric]["macro_f1"] for run in runs]
            summary[name][metric] = {
                "roc_auc_mean": float(np.mean(aucs)), "roc_auc_std": float(np.std(aucs)),
                "macro_f1_mean": float(np.mean(f1s)), "macro_f1_std": float(np.std(f1s)),
            }
    return summary, out_of_fold


def kappa(first, second):
    return float(cohen_kappa_score(first, second)) if len(set(first + second)) > 1 else None


def annotator_agreement(scenarios, out_of_fold, rows):
    position = {(item["requirement_id"], item["slot"]): index for index, item in enumerate(scenarios)}
    rows = [(position[(row["requirement_id"], row["slot"])], row["labels"]) for row in rows
            if (row["requirement_id"], row["slot"]) in position]
    result = {"count": len(rows), "metrics": {}}
    for column, metric in enumerate(METRICS):
        judged = [labels[metric] for _, labels in rows]
        generated = [scenarios[index]["labels"][metric] for index, _ in rows]
        predicted = [out_of_fold[index, column] for index, _ in rows]
        result["metrics"][metric] = {
            "agreement": float(np.mean([a == b for a, b in zip(judged, generated)])),
            "kappa": kappa(judged, generated),
            "model_roc_auc": float(roc_auc_score(judged, predicted)) if len(set(judged)) > 1 else None,
        }
    return result


def pairwise_agreement(by_annotator):
    result = {}
    names = sorted(by_annotator)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            common = sorted(set(by_annotator[first]) & set(by_annotator[second]))
            if not common:
                continue
            result[f"{first} vs {second}"] = {"count": len(common), **{
                metric: kappa([by_annotator[first][key][metric] for key in common],
                              [by_annotator[second][key][metric] for key in common])
                for metric in METRICS
            }}
    return result


def gold_agreement(scenarios, out_of_fold, gold):
    if not gold:
        return None
    by_annotator = {}
    for row in gold:
        by_annotator.setdefault(row["annotator"], {})[(row["requirement_id"], row["slot"])] = row["labels"]
    return {
        "annotators": {
            name: annotator_agreement(scenarios, out_of_fold, [row for row in gold if row["annotator"] == name])
            for name in sorted(by_annotator)
        },
        "pairwise": pairwise_agreement(by_annotator),
    }


def print_gold(gold):
    print("Сравнение с независимой разметкой:")
    for name, result in gold["annotators"].items():
        print(f"  {name} ({result['count']} сценариев):")
        for metric, value in result["metrics"].items():
            print(f"    {metric}: совпадение {value['agreement']:.0%}, каппа {value['kappa']}, ROC-AUC модели {value['model_roc_auc']}")
    for pair, value in gold["pairwise"].items():
        print(f"  {pair} ({value['count']} общих): " + ", ".join(f"{metric} {value[metric]}" for metric in METRICS))


def train():
    scenarios = load_jsonl(TRAIN_SCENARIOS_PATH)
    requirement_texts = {item["id"]: item["text"] for item in json.loads(TRAIN_REQUIREMENTS_PATH.read_text(encoding="utf-8"))}
    x, y = dataset(scenarios, requirement_texts)
    position = {id(item): index for index, item in enumerate(scenarios)}
    parts = {name: [position[id(item)] for item in items] for name, items in split_by_requirement(scenarios).items()}
    print({name: len(index) for name, index in parts.items()})
    net, history, threshold, test, _ = fit_and_score(x, y, scenarios, parts["train"], parts["val"], parts["test"])
    print(f"Порог, подобранный на validation: {threshold:.2f}")
    print(f"Кросс-валидация по требованиям, {CV_FOLDS} разбиений:")
    cross_validation, out_of_fold = cross_validate(x, y, scenarios)
    gold = gold_agreement(scenarios, out_of_fold, load_jsonl(GOLD_PATH))
    report = {
        "split": {name: sorted({scenarios[i]["requirement_id"] for i in index}) for name, index in parts.items()},
        "threshold": threshold,
        "history": history,
        "test": test,
        "cross_validation": cross_validation,
        "gold": gold,
    }
    MODEL_PATH.parent.mkdir(exist_ok=True)
    torch.save({"state": net.state_dict(), "size": x.shape[1], "threshold": threshold}, MODEL_PATH)
    TRAINING_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, result in cross_validation.items():
        print(name, {metric: f"{value['roc_auc_mean']:.2f}±{value['roc_auc_std']:.2f}" for metric, value in result.items()})
    if gold:
        print_gold(gold)
    return net, report


def predict(net, cases, requirement):
    with torch.no_grad():
        probabilities = torch.sigmoid(net(features(cases, [requirement] * len(cases)))).numpy()
    return [dict(zip(METRICS, map(float, row))) for row in probabilities]


if __name__ == "__main__":
    train()
