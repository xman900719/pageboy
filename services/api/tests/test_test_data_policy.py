"""开发环境虚构测试数据必须 Owner 批准的门禁回归。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from test_data_policy import require_owner_test_data_approval  # noqa: E402


def test_requires_explicit_owner_approval(monkeypatch):
    monkeypatch.delenv("PAGEBOY_OWNER_TEST_DATA_APPROVED", raising=False)
    monkeypatch.delenv("PAGEBOY_OWNER_APPROVAL_REF", raising=False)
    with pytest.raises(SystemExit, match="拒绝写入开发环境虚构测试数据"):
        require_owner_test_data_approval("unit-test")


def test_requires_both_flag_and_reference(monkeypatch):
    monkeypatch.setenv("PAGEBOY_OWNER_TEST_DATA_APPROVED", "1")
    monkeypatch.delenv("PAGEBOY_OWNER_APPROVAL_REF", raising=False)
    with pytest.raises(SystemExit):
        require_owner_test_data_approval("unit-test")


def test_approved_reference_is_returned(monkeypatch):
    monkeypatch.setenv("PAGEBOY_OWNER_TEST_DATA_APPROVED", "1")
    monkeypatch.setenv("PAGEBOY_OWNER_APPROVAL_REF", "owner-test-2026-11-15")
    assert require_owner_test_data_approval("unit-test") == "owner-test-2026-11-15"
