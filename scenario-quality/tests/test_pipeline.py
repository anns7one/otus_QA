import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import report
from generate_cases import ACCEPTED, NOT_DEFINED, REJECTED, apply_rules, check_review, stated_outcome, value_outcome
from quality_model import QualityNet, split_by_requirement

NAME = {"mandatory": True, "min_length": 1, "max_length": 50, "allowed": ["кириллица", "латиница строчная", "латиница заглавная", "дефис"],
        "required": [], "edge_spaces": "обрезаются", "max_middle_spaces": 1, "exact_symbols": [], "mask": ""}
EMAIL = {"mandatory": True, "min_length": 1, "max_length": 0, "allowed": ["латиница строчная", "цифры", "точка"],
         "required": [], "edge_spaces": "ошибка", "max_middle_spaces": 0, "exact_symbols": [{"symbol": "@", "count": 1}], "mask": ""}
PHONE = {"mandatory": True, "min_length": 0, "max_length": 0, "allowed": ["цифры"], "required": ["цифры"],
         "edge_spaces": "не сказано", "max_middle_spaces": 0, "exact_symbols": [], "mask": "+7(...)...-..-.."}


def test_value_outcome_follows_field_rules():
    assert value_outcome("а", NAME) == ACCEPTED
    assert value_outcome("  Анна-Мария Ли  ", NAME) == ACCEPTED
    assert value_outcome("Анна Мария Ли", NAME) == REJECTED
    assert value_outcome("Анна2", NAME) == REJECTED
    assert value_outcome("строка из 51 символа", NAME) == REJECTED
    assert value_outcome(" a@b.ru", EMAIL) == REJECTED
    assert value_outcome("a@@b.ru", EMAIL) == REJECTED
    assert value_outcome("строка из 1000 символов", EMAIL) == NOT_DEFINED
    assert value_outcome("+7(912)345-67-89", PHONE) == ACCEPTED
    assert value_outcome("+7(912)345-67", PHONE) == REJECTED
    assert value_outcome("+7(912)345-67-891", PHONE) == NOT_DEFINED


def test_stated_outcome_reads_model_wording():
    assert stated_outcome("Значение невалидно") == REJECTED
    assert stated_outcome("Ввод отклоняется") == REJECTED
    assert stated_outcome("Кнопка неактивна") == REJECTED
    assert stated_outcome("Поведение не задано требованием, нужно уточнение") == NOT_DEFINED
    assert stated_outcome("Пользователь регистрируется") == ACCEPTED


def test_apply_rules_does_not_accept_in_free_cases():
    case = {"steps": ["Ввести а"], "expected_result": "Появляется ошибка уникальности",
            "boundary_values": [{"value": "а", "expected": "ошибка"}]}
    assert apply_rules(case, NAME, format_only=False) == 0
    assert apply_rules(case, NAME, format_only=True) == 2
    assert case["expected_result"] == "Значение принимается"


def test_check_review_rejects_changed_requirement(tmp_path, monkeypatch):
    import generate_cases
    review = tmp_path / "review.json"
    review.write_text('{"requirement_sha256": "old", "field_rules": {}}', encoding="utf-8")
    monkeypatch.setattr(generate_cases, "REVIEW_PATH", review)
    try:
        check_review("новый текст")
    except SystemExit as error:
        assert "изменилось" in str(error)
    else:
        raise AssertionError("изменённое требование прошло проверку")


def test_split_by_requirement_has_no_leak():
    scenarios = [{"requirement_id": f"DS-{i:02d}"} for i in range(20) for _ in range(8)]
    parts = split_by_requirement(scenarios)
    ids = {name: {item["requirement_id"] for item in items} for name, items in parts.items()}
    assert not ids["train"] & ids["val"] and not ids["train"] & ids["test"] and not ids["val"] & ids["test"]
    assert sum(len(items) for items in parts.values()) == len(scenarios)


def test_net_can_overfit_small_batch():
    torch.manual_seed(0)
    x, y = torch.randn(16, 32), torch.randint(0, 2, (16, 4)).float()
    net = QualityNet(32)
    optimizer = torch.optim.Adam(net.parameters(), lr=1e-2)
    for _ in range(300):
        optimizer.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(net(x), y)
        loss.backward()
        optimizer.step()
    assert loss.item() < 0.05


def test_markdown_report_format(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "REPORT_PATH", tmp_path / "report.md")
    results = {"summary": {"total": 2, "passed": 1, "failed": 1}, "scenarios": [
        {"id": "TC-001", "title": "a | b", "quality": "Высокое", "score": 0.9},
        {"id": "TC-002", "title": "c", "quality": "Низкое", "score": 0.2},
    ]}
    report.write_markdown(results, "plots/scores.png")
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert text.startswith("# Отчёт о тестировании сценариев\n")
    assert "- Успешные: 1" in text and "- Неуспешные: 1" in text
    assert "](plots/scores.png)" in text
    assert "## Список сценариев\n\n| Описание | Качество | Оценка |" in text
    assert "| TC-001 a \\| b | Высокое | 0.90 |" in text
