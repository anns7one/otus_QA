"""Разбор pytest-файлов в структуру: тесты, шаги, сигнатура.

Шаг 3 плана: AST вместо regex, потому что regex ломается на переносах строк,
f-строках и разном порядке kwargs, а ast понимает структуру кода. Тесты не
запускаются — нам нужно, что тест делает, а не проходит ли он.
"""
import ast
import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

REQUEST_METHODS = {"get", "post", "put", "patch", "delete"}

# Имена, которые НЕ обезличиваем при нормализации шага: это не переменные,
# а значимые операции/типы. Если заменить и их, isinstance(x, int) и
# isinstance(x, str) стали бы одинаковой строкой — потеряли бы разницу.
_KEEP_NAMES = {
    "len", "isinstance", "type", "sorted", "all", "any",
    "set", "dict", "list", "tuple", "int", "str", "float", "bool",
}


@dataclass
class Signature:
    method: str | None
    path: str | None
    status: int | None
    params: frozenset

    def key(self):
        """Ключ для группировки тестов с одинаковой сигнатурой (шаг 5, барьер)."""
        return (self.method, self.path, self.status, self.params)


@dataclass
class Step:
    kind: str          # "request" или "assert"
    normalized: str    # каноническая форма для сравнения между тестами
    lineno: int


@dataclass
class Test:
    __test__ = False  # не тестовый класс pytest, а доменная модель — не собирать

    name: str
    file: str
    lineno: int
    loc: int
    docstring: str | None
    signature: Signature
    steps: list[Step]
    node: ast.FunctionDef = field(repr=False)


def _url_from_arg(node) -> str | None:
    """Достаёт URL из f-строки (JoinedStr) или склейки BASE_URL + '...' (BinOp)."""
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
                parts.append(f"{{{value.value.id}}}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _url_from_arg(node.left)
        right = _url_from_arg(node.right)
        return (left or "") + (right or "") if left is not None and right is not None else None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return f"{{{node.id}}}"
    return None


def normalize_path(url: str) -> str:
    """Убирает имя базовой переменной и заменяет числовые id на {id}."""
    path = url.replace("{BASE_URL}", "")
    return re.sub(r"/\d+", "/{id}", path) or "/"


def _find_request_call(node: ast.FunctionDef):
    for child in ast.walk(node):
        if (isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "requests"
                and child.func.attr in REQUEST_METHODS):
            url_arg = child.args[0] if child.args else None
            return child.func.attr.upper(), url_arg, child.keywords
    return None


def _extract_params(keywords) -> frozenset:
    for kw in keywords:
        if kw.arg == "params" and isinstance(kw.value, ast.Dict):
            return frozenset(str(k.value) for k in kw.value.keys if isinstance(k, ast.Constant))
    return frozenset()


def _extract_status(node: ast.FunctionDef):
    for child in ast.walk(node):
        if (isinstance(child, ast.Assert) and isinstance(child.test, ast.Compare)
                and isinstance(child.test.left, ast.Attribute)
                and child.test.left.attr == "status_code"
                and isinstance(child.test.ops[0], ast.Eq)):
            comparator = child.test.comparators[0]
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, int):
                return comparator.value
    return None


def build_signature(node: ast.FunctionDef) -> Signature:
    call = _find_request_call(node)
    if call is None:
        return Signature(None, None, None, frozenset())
    method, url_arg, keywords = call
    url = _url_from_arg(url_arg) if url_arg is not None else None
    return Signature(
        method=method,
        path=normalize_path(url) if url else None,
        status=_extract_status(node),
        params=_extract_params(keywords),
    )


class _Anonymizer(ast.NodeTransformer):
    """Обезличивает имена переменных, оставляет значимые имена (типы, len,
    isinstance...), сортирует множества и словари, чтобы порядок записи в
    исходном коде не влиял на сравнение."""

    def visit_Name(self, node):
        if node.id in _KEEP_NAMES:
            return node
        return ast.copy_location(ast.Name(id="VAR", ctx=node.ctx), node)

    def visit_Set(self, node):
        self.generic_visit(node)
        node.elts.sort(key=ast.unparse)
        return node

    def visit_Dict(self, node):
        self.generic_visit(node)
        pairs = sorted(zip(node.keys, node.values), key=lambda kv: ast.unparse(kv[0]))
        node.keys = [k for k, _ in pairs]
        node.values = [v for _, v in pairs]
        return node


def normalize_step(node) -> str:
    """Каноническая текстовая форма шага для сравнения между тестами."""
    clone = copy.deepcopy(node)
    return ast.unparse(_Anonymizer().visit(clone))


def extract_steps(node: ast.FunctionDef) -> list[Step]:
    steps = []
    for child in ast.walk(node):
        if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                and isinstance(child.func.value, ast.Name) and child.func.value.id == "requests"
                and child.func.attr in REQUEST_METHODS):
            url = _url_from_arg(child.args[0]) if child.args else None
            path = normalize_path(url) if url else "?"
            steps.append(Step("request", f"{child.func.attr.upper()} {path}", child.lineno))
        elif isinstance(child, ast.Assert):
            steps.append(Step("assert", f"ASSERT {normalize_step(child.test)}", child.lineno))
    return steps


def load_tests(directory: str) -> list[Test]:
    tests = []
    for path in sorted(Path(directory).glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                tests.append(Test(
                    name=node.name,
                    file=path.name,
                    lineno=node.lineno,
                    loc=node.end_lineno - node.lineno + 1,
                    docstring=ast.get_docstring(node),
                    signature=build_signature(node),
                    steps=extract_steps(node),
                    node=node,
                ))
    return tests
