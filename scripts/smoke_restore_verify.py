#!/usr/bin/env python3
"""ST-OPS-01 异地恢复演练冒烟：对"已恢复"的数据库与附件目录做端到端验证。

用法（演练环境；不触碰生产）：
  .venv/bin/python scripts/smoke_restore_verify.py \
      --database-url postgresql+psycopg://drill:drill@127.0.0.1:55432/pageboy_drill \
      --attachments-dir /tmp/drill-attachments \
      [--api-port 18790] [--token 演练令牌] [--expect-counts counts.json]

验证项：
  1. 临时起 API 指向恢复库 → /health/live 与 /health/ready 就绪；
  2. 练习可服务（/api/practice/next 返回可作答题干）；
  3. 作答溯源列表结构有效（每条含 11 个既定键、scoring_origin ∈ 已知来源）；
  4. 恢复库 alembic 版本 == 本仓库当前 head（防"旧库跑新代码"）；
  5. 附件联合一致性：source_attachments 每行 storage_key 对应恢复目录中的文件，
     sha256 与字节数逐一致；并经下载路由抽样一个附件做字节级比对；
  6. --expect-counts：与备份时刻记录的行数基线逐表比对。

已知副作用（如实声明，非只读）：第 2 项的练习取题会按业务语义落一条训练曝光
（ST-004：next 即曝光）。行数基线比对先于该调用执行，基线应为"备份时刻"行数；
该曝光行属演练痕迹，真实演练记录中注明即可。

诚实边界：本脚本只证明"恢复产物自洽可用"；异地/另一故障域、真实 RTO/RPO 仍由
docs/operations/backup-policy.md 的实际演练记录证明，不因本脚本绿而视为 AC-OPS-01。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
from shutong import models as m  # noqa: E402

ATTEMPT_KEYS = {"id", "question_version_id", "purpose", "kind", "answer", "earned_points",
                "max_points", "scoring_origin", "hints_used", "self_assessment", "created_at"}
KNOWN_ORIGINS = {"reviewed_answer_key", "ungraded_subjective"}


def log(message: str) -> None:
    print(f"[ST-OPS-01-VERIFY] {message}", flush=True)


def start_api(api_dir: Path, venv_python: Path, port: int, env: dict[str, str]) -> subprocess.Popen:
    # 必须子进程启动：shutong.database 在导入时读取 DATABASE_URL，进程内导入会拿错引擎。
    process = subprocess.Popen(
        [str(venv_python), "-m", "uvicorn", "shutong.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=api_dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"临时 API 进程退出 code={process.returncode}（检查 database-url/attachments-dir）")
        try:
            if httpx.get(f"{base}/health/live", timeout=2, trust_env=False).status_code == 200:
                return process
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    process.terminate()
    raise RuntimeError("临时 API 20 秒未就绪")


def main() -> int:
    parser = argparse.ArgumentParser(description="ST-OPS-01 恢复产物冒烟（只读）")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--attachments-dir", required=True, type=Path)
    parser.add_argument("--api-port", type=int, default=18790)
    parser.add_argument("--token", default="drill-secret")
    parser.add_argument("--expect-counts", type=Path, default=None,
                        help="JSON 文件 {表名: 行数}，与恢复库逐表比对")
    args = parser.parse_args()

    url = make_url(args.database_url)
    db_name = url.database or ""
    log(f"目标库: {db_name}@{url.host}:{url.port}；附件目录: {args.attachments_dir.resolve()}")
    if not db_name.startswith("pageboy"):
        log(f"警告：目标库名 '{db_name}' 非隔离演练命名——请人工确认这不是生产库（冒烟除一条演练曝光外不写库，仍请核对目标）。")

    engine = create_engine(args.database_url,
                           connect_args={"connect_timeout": 5} if args.database_url.startswith("postgresql") else {})
    try:
        failures: list[str] = []

        # 4) alembic 版本 == 仓库 head（在起 API 前查，避免旧库跑新代码的误判）。
        api_dir = Path(__file__).resolve().parents[1] / "services" / "api"
        venv_python = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
        head = subprocess.run([str(venv_python), "-m", "alembic", "heads"], cwd=api_dir,
                              capture_output=True, text=True, check=True).stdout.split()[0]
        with engine.connect() as connection:
            version = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        if version != head:
            failures.append(f"迁移版本不一致：恢复库={version}，仓库 head={head}（restore.sh 应已告警）")
        else:
            log(f"迁移版本一致：{version}")

        # 6) 可选行数基线比对。
        if args.expect_counts:
            expected = json.loads(args.expect_counts.read_text(encoding="utf-8"))
            with engine.connect() as connection:
                for table, want in expected.items():
                    got = connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar()
                    if got != want:
                        failures.append(f"行数不符 {table}: 期望 {want}，实际 {got}")
                    else:
                        log(f"行数一致 {table}={got}")
        else:
            log("未提供 --expect-counts：跳过行数基线比对（推荐演练时提供）")

        # 1) 临时 API 就绪（子进程；shutong.database 在导入时读 DATABASE_URL）。
        env = dict(os.environ, DATABASE_URL=args.database_url, SHUTONG_TOKEN=args.token,
                   SHUTONG_PRIVATE_DIR=str(args.attachments_dir.resolve()), PYTHONPATH=str(api_dir))
        api_process = start_api(api_dir, venv_python, args.api_port, env)
        base = f"http://127.0.0.1:{args.api_port}"
        headers = {"Authorization": f"Bearer {args.token}"}
        try:
            with httpx.Client(base_url=base, headers=headers, timeout=15, trust_env=False) as client:
                for path in ("/health/live", "/health/ready"):
                    response = client.get(path)
                    if response.status_code != 200:
                        failures.append(f"{path} -> {response.status_code}")
                log("健康检查：live/ready 就绪" if not any("health" in f for f in failures)
                    else "健康检查失败")

                # 2) 练习可服务。
                next_item = client.get("/api/practice/next?subject=math&purpose=training")
                if next_item.status_code != 200 or not next_item.json().get("stem"):
                    failures.append(f"练习取题失败：HTTP {next_item.status_code} {next_item.text[:120]}")
                else:
                    log(f"练习可服务：{next_item.json()['stem'][:30]}…")

                # 3) 溯源列表结构。
                attempts = client.get("/api/practice/attempts?subject=math")
                if attempts.status_code != 200:
                    failures.append(f"attempts 列表 HTTP {attempts.status_code}")
                else:
                    rows = attempts.json()
                    bad = [row for row in rows if set(row) != ATTEMPT_KEYS
                           or row["scoring_origin"] not in KNOWN_ORIGINS]
                    if bad:
                        failures.append(f"attempts 结构异常 {len(bad)} 条（键集/来源）")
                    else:
                        log(f"作答溯源列表：{len(rows)} 条，结构/来源有效")

                # 5) 附件联合一致性（DB 行 ↔ 磁盘文件 ↔ 下载路由）。
                with engine.connect() as connection:
                    records = connection.execute(select(m.SourceAttachment.id, m.SourceAttachment.sha256,
                                                        m.SourceAttachment.byte_size,
                                                        m.SourceAttachment.storage_key)).all()
                if not records:
                    log("警告：恢复库中无 source_attachments 行——联合附件一致性未验证（若备份含附件则为异常，请人工核对）")
                else:
                    for record in records:
                        blob = args.attachments_dir / record.storage_key
                        if not blob.is_file():
                            failures.append(f"附件文件缺失：{blob}")
                            continue
                        data = blob.read_bytes()
                        if sha256(data).hexdigest() != record.sha256 or len(data) != record.byte_size:
                            failures.append(f"附件校验失败：{record.id}（DB sha/size 与磁盘不符）")
                    sample = records[0]
                    downloaded = client.get(f"/api/admin/attachments/{sample.id}/download")
                    if downloaded.status_code != 200 or sha256(downloaded.content).hexdigest() != sample.sha256:
                        failures.append(f"附件下载路由校验失败：{sample.id}")
                    else:
                        log(f"附件联合一致性：{len(records)} 行 DB↔磁盘全对；抽样下载字节级一致（{sample.id}）")
        finally:
            api_process.terminate()
            api_process.wait(timeout=10)

        if failures:
            log("FAIL：")
            for failure in failures:
                log(f"  - {failure}")
            return 1
        log("RESTORE SMOKE PASSED（恢复产物自洽可用）。仍需按 backup-policy 记录演练时间/快照ID/校验结果，方构成 AC-OPS-01。")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
