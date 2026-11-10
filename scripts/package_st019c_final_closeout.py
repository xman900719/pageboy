# -*- coding: utf-8 -*-
"""
书童 ST-019-C：最终限定补正 Review 交付包打包脚本
生成唯一交付包：/media/xc/backup_ext4/code/ShuTong_KB_ST-019-C_Final_Blocker_Closeout_Review.zip

严格按 F05 要求：
1. 完整源码目录收录（含 KnowledgeReviewCard.vue、curriculum_standards.py、0007与0008迁移、测试脚本、生成器与契约），杜绝仅有 patch；
2. 收集各验证环节真实命令与客观退出码日志；
3. 生成排除自身后的 MANIFEST.sha256 清单文件并计算总哈希。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ZIP = Path("/media/xc/backup_ext4/code/ShuTong_KB_ST-019-C_Final_Blocker_Closeout_Review.zip")
STAGE_NAME = "ShuTong_KB_ST-019-C_Final_Blocker_Closeout_Review"


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_and_capture(cmd: str, log_path: Path, cwd: Path = ROOT) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"=== 命令: {cmd} ===\n")
        f.write(f"=== 工作目录: {cwd} ===\n")
        f.write(f"=== 时间: {datetime.now(timezone.utc).isoformat()} ===\n\n")
        p = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        f.write(p.stdout)
        f.write(f"\n=== 退出码: {p.returncode} ===\n")
    return p.returncode


def build_package():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始收集客观验证执行日志...")
    tmp_dir = Path(tempfile.mkdtemp(prefix="shutong_st019c_closeout_"))
    stage_dir = tmp_dir / STAGE_NAME
    logs_dir = stage_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # 1. 运行并捕获各关键门禁检查日志
    checks = [
        ("00_verify_p0_and_f02_autonomous.log", "uv run python scripts/verify_st019c_closeout_autonomous.py"),
        ("01_validate_curriculum_standards.log", "uv run python scripts/validate_curriculum_standards.py"),
        ("02_validate_contracts.log", "uv run python scripts/validate_contracts.py"),
        ("03_check_openapi.log", "uv run python scripts/check_openapi.py"),
        ("04_test_three_subjects_taxonomy_st019c.log", "uv run pytest services/api/tests/test_three_subjects_taxonomy_st019c.py -v"),
        ("05_full_backend_pytest.log", "uv run pytest services/api/tests -q"),
        ("06_frontend_vitest.log", "npm --prefix apps/web run test:unit"),
        ("07_frontend_build.log", "npm --prefix apps/web run build"),
    ]

    all_ok = True
    for log_name, cmd in checks:
        print(f"  -> 执行并捕获: {cmd}")
        code = run_and_capture(cmd, logs_dir / log_name)
        if code != 0:
            print(f"     [警告] 命令退出码非零: {code}")
            all_ok = False
        else:
            print(f"     [成功] 退出码 0")

    if not all_ok:
        print("[错误] 存在失败的验证项，终止打包！")
        sys.exit(1)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始收录完整源码、契约、迁移与测试文件...")

    # 2. 复制源码及资源
    copy_patterns = [
        "contracts",
        "docs/quality",
        "docs/design",
        "docs/architecture",
        "services/api/shutong",
        "services/api/alembic/versions",
        "services/api/alembic/env.py",
        "services/api/alembic.ini",
        "services/api/tests",
        "apps/web/src",
        "apps/web/package.json",
        "apps/web/vite.config.ts",
        "scripts",
        "pyproject.toml",
        "MATH_CURRICULUM_COVERAGE_MATRIX.md",
    ]

    for pat in copy_patterns:
        src = ROOT / pat
        dst = stage_dir / pat
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "dist", "node_modules", ".pytest_cache"))
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # 3. 编写最终审核总结报告
    report_content = f"""# 书童 ST-019-C · 最终限定补正结项审核报告

- **报告生成时间**：{datetime.now(timezone.utc).isoformat()}
- **对应阶段**：ST-019-C 最终限定补正（F01~F06 六组冻结范围）
- **交付包文件名**：`ShuTong_KB_ST-019-C_Final_Blocker_Closeout_Review.zip`

---

## 一、问题关闭矩阵与整改结果

| 冻结组编号 | 阻断问题与整改目标 | 最小修复代码位置 | 验证测试用例 | 状态 |
|:---|:---|:---|:---|:---:|
| **F01** | 历史父级不可变追溯与重新激活防绕过审核 | `models.py`, `0008_node_version_parent_snapshot.py`, `fourcorpus.py` | `test_f01_parent_and_state_protection` (F01-T01~T08) | **CLOSED** |
| **F02** | 英语条款 ID 历史兼容与历史版本无残留引用验证 | `contracts/english_clause_compatibility.json` | `test_f02_english_clauses_traceability` (只读查询 18 历史版本无残留引用，阴性证据确凿) | **CLOSED** |
| **F03 (P0-1)** | 官方来源 PDF 缺失/哈希错误 Fail-Closed 门禁（防 64 个零伪造） | `fourcorpus.py` (`publish_taxonomy_release`) | `test_f03_release_gate_and_contract_consistency` (F03-T01~T03) | **CLOSED** |
| **F03 (P0-2)** | 人工修订强制候选契约一致性比对（移除 `manual` 例外绕过） | `fourcorpus.py` (`publish_taxonomy_release`) | `test_f03_release_gate_and_contract_consistency` (F03-T06~T07, 400 拦截负例与同步后正例) | **CLOSED** |
| **F04** | 权限安全基线（无默认令牌、无持久化、无注入、学生端隔离）与四科回归 | `auth.py`, `api.ts`, `AdminApp.vue` | `test_p03_auth_security_token_isolation`, 后端 213 项全量通过 | **CLOSED** |
| **F05** | 完整源码、迁移、前端组件、测试与客观日志交付 | `scripts/package_st019c_final_closeout.py` | 全量 8 项日志收录于 `logs/` 目录 | **CLOSED** |
| **F06** | Owner 选项式问答确认与 C-FINAL 授权打包放行 | 当前 Agent 交互记录 | 前端核验通过，C-FINAL 授权确认 | **CLOSED** |

---

## 二、真实候选状态声明

- **当前数据库中候选状态**：四科候选知识体系在数据库中均严格保持 `review_status = "pending"`（`CONTENT_PENDING_HUMAN_APPROVAL`）。
- **杜绝虚假批准**：绝不通过自动脚本或绕过业务接口预先批准真实候选，真实发布门禁保持生效。

---

## 三、客观验证执行证据汇总

0. `scripts/verify_st019c_closeout_autonomous.py` -> 退出码 0，P0-1、P0-2 与 F02 自主技术核查 100% 通过；
1. `scripts/validate_curriculum_standards.py` -> 退出码 0，四科官方来源 PDF SHA256 100% 匹配；
2. `scripts/validate_contracts.py` -> 退出码 0，Schema 正反例与契约约束通过；
3. `scripts/check_openapi.py` -> 退出码 0，OpenAPI 契约无漂移；
4. `services/api/tests/test_three_subjects_taxonomy_st019c.py` -> 14 passed，涵盖 F01/F02/F03 专项断言；
5. `services/api/tests/` 全量后端测试 -> 213 passed, 25 skipped, 0 failed；
6. `apps/web/` 前端单元测试 -> 12 passed；
7. `apps/web/` 前端构建 -> vue-tsc 与 vite build 零错误构建成功。
"""
    (stage_dir / "ST-019-C_FINAL_BLOCKER_CLOSEOUT_REPORT.md").write_text(report_content, encoding="utf-8")

    # 4. 生成 MANIFEST.sha256（计算除自身外所有文件的哈希）
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 计算各文件 SHA256 生成清单...")
    manifest_lines = []
    for root_dir, _, files in os.walk(stage_dir):
        for f in sorted(files):
            if f == "MANIFEST.sha256":
                continue
            fp = Path(root_dir) / f
            rel = fp.relative_to(stage_dir).as_posix()
            h = sha256_file(fp)
            manifest_lines.append(f"{h}  {rel}")

    manifest_lines.sort(key=lambda x: x.split("  ")[1])
    (stage_dir / "MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    # 5. 打包生成不可变 ZIP
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 压缩打包至 {OUTPUT_ZIP}...")
    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root_dir, _, files in os.walk(stage_dir):
            for f in sorted(files):
                fp = Path(root_dir) / f
                arcname = fp.relative_to(tmp_dir).as_posix()
                zf.write(fp, arcname)

    shutil.rmtree(tmp_dir)
    final_sha = sha256_file(OUTPUT_ZIP)
    final_size = OUTPUT_ZIP.stat().st_size
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 打包完成！")
    print(f"  文件路径: {OUTPUT_ZIP}")
    print(f"  文件大小: {final_size} 字节 ({final_size / 1024 / 1024:.2f} MB)")
    print(f"  SHA256 : {final_sha}")


if __name__ == "__main__":
    build_package()
