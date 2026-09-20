import json
from pathlib import Path

import pytest

_results = []


@pytest.fixture
def record_result():
    def _record(payload, passed, data):
        _results.append({
            "id": payload["id"],
            "class": payload["class"],
            "passed": passed,
            "reply": (data.get("reply") or "")[:200],
        })
    return _record


def pytest_sessionfinish(session, exitstatus):
    report_path = Path(__file__).parent / "security_test_report.md"
    passed_count = sum(1 for r in _results if r["passed"])
    lines = [
        "# Security Test Report",
        "",
        f"**Total: {passed_count}/{len(_results)} passed**",
        "",
        "| ID | Class | Result | Reply (truncated) |",
        "|---|---|---|---|",
    ]
    for r in _results:
        status = "PASS" if r["passed"] else "FAIL"
        reply = r["reply"].replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['class']} | {status} | {reply} |")
    report_path.write_text("\n".join(lines), encoding="utf-8")
