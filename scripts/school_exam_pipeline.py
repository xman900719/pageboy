#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校考试卷本地流水线：扫描 → 卷头识别 → 严格匹配 → 私有待核对入库。

用法：
  uv run python scripts/school_exam_pipeline.py scan  --env development
  uv run python scripts/school_exam_pipeline.py scan  --env development --source-dir ~/授权试卷目录
  uv run python scripts/school_exam_pipeline.py run   --env development --source-dir ~/授权试卷目录
  uv run python scripts/school_exam_pipeline.py acquire --env development

安全边界：
- `--dry-run` 严格只读：不建目录、不复制文件、不写数据库、不调用 API。
- `acquire` 只调用仓库中已登记且通过授权审查的真实来源适配器；当前未配置时明确返回
  SOURCE_NOT_CONFIGURED，绝不猜测 URL 或伪造远程下载成功。
- 普通 scan 只登记为待核对，不自动确认总分；run 仅自动归档唯一精确匹配的原卷附件。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

DEFAULT_DEV_API = "http://127.0.0.1:8000"
DEFAULT_PROD_API = "http://127.0.0.1:8180"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="书童 · 校考试卷自动发现与匹配流水线")
    parser.add_argument("command", choices=("scan", "acquire", "run"))
    parser.add_argument("--env", choices=("development", "production"), default="development")
    parser.add_argument(
        "--source-dir",
        default="",
        help="已获授权的本地试卷目录；扫描后会复制到当前环境私有 inbox，原文件不变",
    )
    parser.add_argument("--dry-run", action="store_true", help="严格只读预演，不产生任何文件/数据库/API 副作用")
    parser.add_argument("--api-url", default="", help="Pageboy Admin API 地址（默认按环境回环端口）")
    parser.add_argument("--admin-token", default="", help="管理端令牌；也可用 SHUTONG_ADMIN_TOKEN")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON（默认输出简明中文摘要）")
    parser.add_argument(
        "--collect-k12100",
        action="store_true",
        help="run 成功后，对唯一精确匹配的试卷启动单场 k12100 采集并等待完成（真实账号未配置时阻断）",
    )
    return parser


def _api_request(base_url: str, path: str, token: str, *, body: dict | None = None) -> dict:
    url = base_url.rstrip("/") + path
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    opener = build_opener(ProxyHandler({})) if (urlparse(url).hostname or "") in {"127.0.0.1", "localhost", "::1"} else build_opener()
    request = Request(url, data=data, headers=headers, method="POST")
    try:
        with opener.open(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {detail[:600]}") from exc
    except URLError as exc:
        raise RuntimeError(f"无法连接 Pageboy API {url}: {exc.reason}") from exc


def _summary(command: str, payload: dict) -> str:
    if command in {"scan", "run"}:
        if payload.get("dry_run"):
            return (
                f"只读预演：{payload.get('file_count', 0)} 份合法试卷，"
                f"{len(payload.get('errors') or [])} 个跳过/错误。未写入任何文件或数据库。"
            )
        run = payload.get("run") or {}
        return (
            f"扫描完成：发现 {run.get('discovered_count', 0)}，"
            f"新增 {max(0, run.get('discovered_count', 0) - run.get('duplicate_count', 0))}，"
            f"去重 {run.get('duplicate_count', 0)}，待核对 {run.get('needs_review_count', 0)}，"
            f"自动归档 {run.get('imported_count', 0)}，错误 {run.get('error_count', 0)}。"
        )
    if command == "acquire":
        return f"真实授权来源已取得 {payload.get('acquired_count', 0)} 份试卷。"
    return "完成。"


def _wait_collection_job(api_url: str, token: str, job_id: str, *, timeout: int = 300) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = _api_request(api_url, f"/api/school-exams/k12100-sync/jobs/{job_id}", token)
        if last.get("state") in {"completed", "failed"}:
            return last
        time.sleep(2.0)
    raise RuntimeError(f"K12100_COLLECTION_TIMEOUT: 任务 {job_id} 在 {timeout} 秒内未完成；last_state={last.get('state')}")


def start_matched_paper_collection(api_url: str, token: str, papers: list[dict], *, timeout: int = 300) -> dict:
    """在本地 run 后为唯一精确匹配试卷启动单场采集；不自动确认总分。"""
    targets = [
        paper
        for paper in papers
        if paper.get("status") in {"matched", "imported"} and paper.get("school_exam_id")
    ]
    if not targets:
        raise RuntimeError("NO_MATCHED_PAPER: 本地扫描没有唯一精确匹配的试卷，未启动 k12100 采集")
    if len(targets) > 1:
        raise RuntimeError(
            f"MULTIPLE_MATCHED_PAPERS: 发现 {len(targets)} 份已匹配试卷，拒绝猜测采集目标；请逐份处理"
        )
    target = targets[0]
    job = _api_request(
        api_url,
        f"/api/school-exams/pipeline/papers/{target['id']}/collect",
        token,
        body={"use_ai": True, "headless": False},
    )
    return _wait_collection_job(api_url, token, str(job.get("job_id") or ""), timeout=timeout)


def _print_result(command: str, payload: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(_summary(command, payload))
    errors = (payload.get("run") or {}).get("errors") or payload.get("errors") or []
    for item in errors[:8]:
        print(f"  - {item.get('path') or '（目录）'}: {item.get('code')}", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _resolve_source_dir(args: argparse.Namespace) -> Path | None:
    if not args.source_dir:
        return None
    raw = Path(args.source_dir).expanduser()
    if raw.is_symlink():
        raise RuntimeError("SOURCE_SYMLINK_REJECTED")
    resolved = raw.resolve()
    if not resolved.is_dir():
        raise RuntimeError("SOURCE_NOT_DIRECTORY")
    return resolved


def _run_dry(args: argparse.Namespace, source_dir: Path | None) -> int:
    from shutong.school_exam_pipeline import PaperPipelineError, preview_local_source, school_exam_inbox

    target = source_dir or school_exam_inbox(args.env)
    if not target.exists():
        print(json.dumps({"dry_run": True, "error": "SOURCE_NOT_FOUND", "path": str(target)}, ensure_ascii=False, indent=2))
        return 1
    try:
        payload = preview_local_source(target, environment=args.env)
    except PaperPipelineError as exc:
        print(json.dumps({"dry_run": True, "error": exc.code}, ensure_ascii=False, indent=2))
        return 1
    _print_result(args.command, payload, as_json=args.json)
    return 0


def _token(args: argparse.Namespace) -> str:
    return (args.admin_token or os.getenv("SHUTONG_ADMIN_TOKEN") or "").strip()


def _api_url(args: argparse.Namespace) -> str:
    if args.api_url:
        return args.api_url.rstrip("/")
    return DEFAULT_PROD_API if args.env == "production" else DEFAULT_DEV_API


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source_dir = _resolve_source_dir(args)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        return _run_dry(args, source_dir)

    os.environ["SHUTONG_ENV"] = args.env
    from shutong.school_exam_pipeline import (
        PaperPipelineError,
        SOURCE_NOT_CONFIGURED,
        school_exam_inbox,
        stage_local_source,
    )

    if source_dir is not None and args.command in {"scan", "run"}:
        try:
            if source_dir.resolve() == school_exam_inbox(args.env).resolve():
                staged = {"errors": [], "staged_count": 0, "duplicate_count": 0}
            else:
                staged = stage_local_source(source_dir, environment=args.env)
        except PaperPipelineError as exc:
            print(json.dumps({"error": exc.code, "message": exc.message}, ensure_ascii=False, indent=2))
            return 1
        if staged["errors"]:
            print(
                f"警告：{len(staged['errors'])} 个文件被安全策略跳过（符号链接/类型/体积/路径）。",
                file=sys.stderr,
            )

    token = _token(args)
    if not token:
        print("错误：调用管理端 API 需要 SHUTONG_ADMIN_TOKEN 或 --admin-token。", file=sys.stderr)
        return 1
    api_url = _api_url(args)
    try:
        if args.command in {"acquire", "run"}:
            try:
                acquired = _api_request(api_url, "/api/school-exams/pipeline/acquire", token, body={})
            except RuntimeError as exc:
                if SOURCE_NOT_CONFIGURED not in str(exc):
                    raise
                if args.command == "acquire":
                    print(json.dumps({"status": "BLOCKED", "error": SOURCE_NOT_CONFIGURED}, ensure_ascii=False, indent=2))
                    return 2
            else:
                _print_result("acquire", acquired, as_json=args.json)
                if args.command == "acquire":
                    return 0

        result = _api_request(
            api_url,
            "/api/school-exams/pipeline/scan",
            token,
            body={"apply_imports": args.command == "run"},
        )
        _print_result(args.command, result, as_json=args.json)
        if args.command == "run" and args.collect_k12100:
            try:
                job = start_matched_paper_collection(api_url, token, result.get("papers") or [])
            except RuntimeError as exc:
                print(json.dumps({"status": "BLOCKED", "error": str(exc)[:500]}, ensure_ascii=False, indent=2))
                return 2
            print(json.dumps({"collection": job}, ensure_ascii=False, indent=2))
            return 0 if job.get("state") == "completed" else 3
        return 0
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
