#!/usr/bin/env python3
"""PreToolUse hook for run_command: enforce Pageboy engineering redlines."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def respond(decision: str, reason: str = "") -> None:
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.exit(0)


def is_checklist_unapproved(content: str) -> bool:
    """Return True if a docs/quality/ manual test checklist is still pending or failed."""
    if "⏳ 待测试人" in content or "总体结论：☐ 放行" in content:
        return True
    # Radio-style judgment items (判定 1..4):
    # - Unchecked 判定 1 (Pass) or checked 判定 2/3/4 (Fail/Halt/Blocked) means unapproved
    if re.search(r"^\s*-\s*\[\s\]\s*\*?\*?判定\s*1", content, flags=re.MULTILINE):
        return True
    if re.search(r"^\s*-\s*\[[xX]\]\s*\*?\*?判定\s*[234]", content, flags=re.MULTILINE):
        return True
    # Table-style option rows where none of ☑ is checked
    if re.search(r"☐\s*通过\s*☐\s*不通过\s*☐\s*阻塞", content):
        return True
    # Any other regular `- [ ]` checkbox (excluding radio options 判定 2/3/4 when 判定 1 is checked)
    for line in content.splitlines():
        if re.match(r"^\s*-\s*\[\s\]\s+", line) and not re.search(r"\*?\*?判定\s*[234]", line):
            return True
    return False


def check_frontend_commit(repo_root: Path, cmd: str) -> None:
    """Enforce AGENTS.md Rule #13 tiered gate on git commit touching apps/web/."""
    if not re.search(r"\bgit\s+commit\b", cmd):
        return

    include_unstaged = bool(re.search(r"\bgit\s+commit\b.*(?:\s-[a-zA-Z]*a|--all\b)", cmd))
    diff_cmds = [["git", "-C", str(repo_root), "diff", "--cached", "--name-only"]]
    if include_unstaged:
        diff_cmds.append(["git", "-C", str(repo_root), "diff", "--name-only"])

    changed_files: set[str] = set()
    for dc in diff_cmds:
        res = subprocess.run(dc, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            changed_files.update(line.strip() for line in res.stdout.splitlines() if line.strip())

    # Check explicit file paths passed to `git commit <path>`
    web_touched = any(f.startswith("apps/web/") for f in changed_files) or ("apps/web/" in cmd)
    if not web_touched:
        return

    # Tier 1: Check if any modified/staged checklist in docs/quality/ is unapproved
    status_res = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    unchecked_files: list[str] = []
    if status_res.returncode == 0:
        for line in status_res.stdout.splitlines():
            path_part = line[3:].strip().split(" -> ")[-1]
            if path_part.startswith("docs/quality/") and path_part.endswith(".md"):
                full_path = repo_root / path_part
                if full_path.is_file():
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    if is_checklist_unapproved(content):
                        unchecked_files.append(path_part)

    if unchecked_files:
        respond(
            "deny",
            f"[AGENTS.md #13 阻断] 检测到前端 (apps/web/) 提交，且核验清单存在未确认通过的测试项: "
            f"{', '.join(unchecked_files)}。请先在 iPadOS 模拟机完成全部人工测试并由测试人勾选确认后再提交。",
        )

    # Tier 2: Host-level force_ask for Owner final approval
    respond(
        "force_ask",
        "[AGENTS.md #13 前端提交门禁] 本次 git commit 包含 apps/web/ 前端变更。"
        "请 Owner 确认：宿主机回环服务 (127.0.0.1:5173) 下的 iPadOS 模拟机选项式人工测试是否已全部通过？",
    )


def main() -> None:
    raw = sys.stdin.read()
    data = json.loads(raw or "{}")
    tool_call = data.get("toolCall") or {}
    if tool_call.get("name") != "run_command":
        respond("allow")

    args = tool_call.get("args") or {}
    cmd = (args.get("CommandLine") or "").strip()
    cwd = Path(data.get("cwd") or "/media/xc/backup_ext4/code/pageboy")

    # 1. Hard Deny: Non-loopback host binding or deprecated port 4173 / script (AGENTS.md #13)
    if re.search(r"--host\s+0\.0\.0\.0\b|0\.0\.0\.0:(?:5173|8000|18765|4173)\b", cmd):
        respond("deny", "[AGENTS.md #13 阻断] 严禁开发或测试服务监听 0.0.0.0，必须仅监听 127.0.0.1。")
    if re.search(r"\brun_manual_test_env\.py\b|--port\s+4173\b|:4173\b", cmd):
        respond("deny", "[AGENTS.md #13/#14 阻断] 端口 4173 与 run_manual_test_env.py 已废弃，请统一使用 scripts/run_dev_env.py。")

    # 2. Hard Deny: Cross-environment access to production paths or legacy ~/.config/shutong
    if re.search(
        r"/media/xc/backup_ext4/pageboy-home/production\b|"
        r"/media/xc/backup_ext4/prod-env/pageboy\b|"
        r"/srv/shutong\b|"
        r"(?:~|\$HOME|/home/xc)/\.config/shutong\b",
        cmd,
    ):
        respond("deny", "[环境隔离阻断] 开发会话严禁读写生产环境受保护路径或已废弃的 ~/.config/shutong。")

    # 3. Hard Deny: Unapproved or agent-forged seed_demo.py execution (AGENTS.md #14)
    if "seed_demo.py" in cmd:
        if "PAGEBOY_OWNER_TEST_DATA_APPROVED=1" in cmd:
            respond(
                "force_ask",
                "[AGENTS.md #14 测试数据门禁] 检测到向开发环境注入虚构演示数据 (seed_demo.py)，必须由 Owner 本人确认批准。",
            )
        elif not os.environ.get("PAGEBOY_OWNER_TEST_DATA_APPROVED"):
            respond(
                "deny",
                "[AGENTS.md #14 阻断] 开发环境默认禁止灌入虚构测试数据 (seed_demo.py fail-closed)。",
            )

    # 4. Tiered Gate: Frontend git commit (AGENTS.md #13)
    check_frontend_commit(cwd, cmd)

    # 5. Force Ask: High-risk R2/R3/R4 operations (push, deploy, rollback, restore, restic prune)
    if re.search(
        r"\bgit\s+push\b|"
        r"\binfra/(?:deploy|rollback|restore)\.sh\b|"
        r"\brestic\s+(?:forget|prune)\b|"
        r"\balembic\s+downgrade\b",
        cmd,
    ):
        if "alembic downgrade" in cmd and "/tmp/" in cmd:
            respond("allow")
        respond(
            "force_ask",
            "[R2/R3/R4 授权门禁] 检测到远程推送、生产部署/回滚、备份清理或数据库降级命令，请 Owner 显式确认后执行。",
        )

    respond("allow")


if __name__ == "__main__":
    main()
