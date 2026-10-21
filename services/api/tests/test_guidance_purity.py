"""AC-GAP-02：guidance 必须保持纯业务函数，更换 OCR/解析实现不得影响它。"""
import ast
import subprocess
import sys
from pathlib import Path

import shutong.guidance as guidance

IMPORT_ALLOWLIST = {"__future__", "dataclasses", "collections", "typing"}

FORBIDDEN_SOURCE_SYMBOLS = [
    "sqlalchemy", "fastapi", "httpx", "pydantic", "pytesseract", "pdfplumber",
    "PIL", "subprocess", "requests", "open(", "__import__", "importlib",
    # os/sys 走 token 级匹配：裸子串会误伤 options/most 等词，但惰性 import 也必须拦下。
    "import os", "import sys", "from os", "from sys",
]


def test_guidance_import_allowlist():
    tree = ast.parse(Path(guidance.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in tree.body:  # 只看模块顶层 import
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    assert roots <= IMPORT_ALLOWLIST


def test_guidance_source_has_no_infrastructure_symbols():
    source = Path(guidance.__file__).read_text(encoding="utf-8")
    for symbol in FORBIDDEN_SOURCE_SYMBOLS:
        assert symbol not in source, f"guidance.py 不得出现基础设施符号：{symbol}"


def test_pure_functions_work_without_infrastructure():
    # 在干净子进程中导入并调用（不 stub 任何环境），防止模块级基础设施依赖悄悄混入。
    api_root = Path(guidance.__file__).resolve().parent.parent
    code = (
        "from shutong.guidance import summarize, make_plan\n"
        "assert summarize([]) == []\n"
        "plan = make_plan([], 90, 100, 15, ['k'])\n"
        "assert plan['steps'][0]['gap_type'] == 'INSUFFICIENT_EVIDENCE'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=api_root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
