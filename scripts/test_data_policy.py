#!/usr/bin/env python3
"""开发环境虚构测试数据/档案的 Owner 批准门禁。

开发环境默认不得自动灌入虚构题目、演示账号数据、虚构校考试卷或测试附件。
只有 Owner 明确批准后，才允许设置以下两个环境变量并运行相关脚本：

    PAGEBOY_OWNER_TEST_DATA_APPROVED=1
    PAGEBOY_OWNER_APPROVAL_REF="<owner-provided-reference>"

自动化 pytest / Playwright 使用临时数据库和临时目录，不属于持久开发环境数据；
它们自身仍需遵守项目测试数据红线（虚构标记、不可进入生产）。
"""

from __future__ import annotations

import os


def require_owner_test_data_approval(purpose: str) -> str:
    """返回审批引用；未获 Owner 批准时 fail-closed（SystemExit）。"""
    approved = os.getenv("PAGEBOY_OWNER_TEST_DATA_APPROVED", "").strip()
    reference = os.getenv("PAGEBOY_OWNER_APPROVAL_REF", "").strip()
    if approved != "1" or not reference:
        raise SystemExit(
            f"拒绝写入开发环境虚构测试数据：{purpose}\n"
            "必须先获得 Owner 明确批准，并设置：\n"
            '  PAGEBOY_OWNER_TEST_DATA_APPROVED=1\n'
            '  PAGEBOY_OWNER_APPROVAL_REF="<owner-provided-reference>"\n'
            "未批准时不会创建/灌入任何虚构题目、校考试卷或测试附件。"
        )
    return reference[:160]
