#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学校考试原卷与答题卡目录批量幂等导入工具。

支持两种运行模式：
1. --api-url（推荐用于运行中的生产/开发服务）：经官方 Admin HTTP API 创建校考并携带
   expected_sha256 上传附件，天然遵循双凭据鉴权与生产用户权限隔离；
2. --direct（用于离线开发环境 SQLite 落库与自动化验证）：直连数据库并复用
   shutong.main.save_school_paper 执行严格文件校验与 0600 私有写入。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from sqlalchemy import select
from shutong import models as m
from shutong.database import make_engine, sessionmaker
from shutong.main import save_school_paper
from shutong.private_files import DOCX_MEDIA_TYPE

# 校考支持科目及中文显示名
SUBJECT_NAMES: dict[str, str] = {
    "math": "数学",
    "physics": "物理",
    "chinese": "语文",
    "english": "英语",
    "ethics": "道法",
}

# 各科默认满分（可通过 --max-points 覆盖）
DEFAULT_MAX_POINTS: dict[str, float] = {
    "math": 100.0,
    "chinese": 100.0,
    "english": 100.0,
    "physics": 70.0,
    "ethics": 50.0,
}

# 支持上传的校考文档媒体类型
EXT_MEDIA_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": DOCX_MEDIA_TYPE,
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# 文件名关键字到科目的映射（按匹配优先级排序）
SUBJECT_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("数学",), "math"),
    (("物理",), "physics"),
    (("语文",), "chinese"),
    (("英语",), "english"),
    (("道法", "道德与法治"), "ethics"),
]


@dataclass
class PlannedAttachment:
    """待导入的单份私有附件描述。"""

    path: Path
    filename: str
    media_type: str
    byte_size: int
    sha256: str


@dataclass
class PlannedExam:
    """按科目归并后的单场学校考试导入计划。"""

    subject: str
    title: str
    exam_date: str
    earned_points: float
    max_points: float
    confirmed_by_user: bool
    attachments: list[PlannedAttachment] = field(default_factory=list)


def detect_subject(filename: str) -> str | None:
    """根据文件名识别对应的校考科目编码。"""
    for keywords, subject in SUBJECT_KEYWORDS:
        if any(kw in filename for kw in keywords):
            return subject
    return None


def _file_sort_key(path: Path) -> tuple[int, str]:
    """确保试卷/题目优先于答题卡排在前面，其余按文件名排序。"""
    name = path.name
    if "卷" in name or "题" in name:
        return (0, name)
    if "答" in name:
        return (1, name)
    return (2, name)


def parse_points_map(spec: str | None) -> dict[str, float]:
    """解析类似 `math=100,physics=70` 的科目分值映射参数。"""
    result: dict[str, float] = {}
    if not spec:
        return result
    for part in spec.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"分值参数格式错误（应为 subject=points）: {item!r}")
        subj, raw_val = item.split("=", 1)
        subj = subj.strip()
        if subj not in SUBJECT_NAMES:
            raise ValueError(f"不支持的校考科目 {subj!r}，可选: {', '.join(SUBJECT_NAMES)}")
        result[subj] = float(raw_val.strip())
    return result


def build_plan_from_dir(
    directory: Path,
    *,
    title_prefix: str,
    exam_date: str,
    max_points_map: dict[str, float] | None = None,
    earned_points_map: dict[str, float] | None = None,
    confirmed_by_user: bool = False,
) -> list[PlannedExam]:
    """扫描本地目录并生成按科目分组的幂等导入计划。"""
    if not directory.is_dir():
        raise FileNotFoundError(f"目标目录不存在: {directory}")
    # 校验日期格式合法性
    date.fromisoformat(exam_date)

    max_map = {**DEFAULT_MAX_POINTS, **(max_points_map or {})}
    earned_map = earned_points_map or {}

    grouped: dict[str, list[Path]] = {}
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        ext = entry.suffix.lower()
        if ext not in EXT_MEDIA_TYPES:
            continue
        subj = detect_subject(entry.name)
        if subj is None:
            continue
        grouped.setdefault(subj, []).append(entry)

    plans: list[PlannedExam] = []
    for subj in ("math", "physics", "chinese", "english", "ethics"):
        files_list = grouped.get(subj)
        if not files_list:
            continue
        ordered = sorted(files_list, key=_file_sort_key)
        attachments = []
        for fpath in ordered:
            data = fpath.read_bytes()
            attachments.append(
                PlannedAttachment(
                    path=fpath,
                    filename=fpath.name,
                    media_type=EXT_MEDIA_TYPES[fpath.suffix.lower()],
                    byte_size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        plans.append(
            PlannedExam(
                subject=subj,
                title=f"{title_prefix} · {SUBJECT_NAMES[subj]}",
                exam_date=exam_date,
                earned_points=float(earned_map.get(subj, 0.0)),
                max_points=float(max_map[subj]),
                confirmed_by_user=confirmed_by_user,
                attachments=attachments,
            )
        )
    return plans


def build_plan_from_manifest(manifest_path: Path) -> list[PlannedExam]:
    """从外部 JSON 清单文件加载自定义校考导入计划。"""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent
    plans: list[PlannedExam] = []
    for item in payload.get("exams", []):
        subj = item["subject"]
        if subj not in SUBJECT_NAMES:
            raise ValueError(f"清单包含不支持的科目: {subj!r}")
        exam_date = item["exam_date"]
        date.fromisoformat(exam_date)
        attachments: list[PlannedAttachment] = []
        for raw_file in item.get("files", []):
            fpath = Path(raw_file)
            if not fpath.is_absolute():
                fpath = (base_dir / fpath).resolve()
            ext = fpath.suffix.lower()
            if ext not in EXT_MEDIA_TYPES:
                raise ValueError(f"不支持的文件类型: {fpath}")
            data = fpath.read_bytes()
            attachments.append(
                PlannedAttachment(
                    path=fpath,
                    filename=fpath.name,
                    media_type=EXT_MEDIA_TYPES[ext],
                    byte_size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        plans.append(
            PlannedExam(
                subject=subj,
                title=item["title"],
                exam_date=exam_date,
                earned_points=float(item.get("earned_points", 0.0)),
                max_points=float(item["max_points"]),
                confirmed_by_user=bool(item.get("confirmed_by_user", False)),
                attachments=attachments,
            )
        )
    return plans


def import_via_direct(
    plans: list[PlannedExam],
    *,
    db_url: str | None = None,
    owner: str = "owner",
    dry_run: bool = False,
) -> dict[str, int]:
    """离线直连数据库与私有附件目录，幂等写入学校考试与原件附件。"""
    stats = {
        "exams_created": 0,
        "exams_existing": 0,
        "attachments_uploaded": 0,
        "attachments_skipped": 0,
    }
    if dry_run:
        return stats

    engine = make_engine(db_url)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as db:
        for plan in plans:
            parsed_date = date.fromisoformat(plan.exam_date)
            existing = db.execute(
                select(m.SchoolExam).where(
                    m.SchoolExam.learner_id == owner,
                    m.SchoolExam.subject == plan.subject,
                    m.SchoolExam.title == plan.title,
                    m.SchoolExam.exam_date == parsed_date,
                )
            ).scalar_one_or_none()
            if existing is not None:
                exam_id = existing.id
                stats["exams_existing"] += 1
            else:
                exam = m.SchoolExam(
                    learner_id=owner,
                    subject=plan.subject,
                    exam_date=parsed_date,
                    title=plan.title,
                    earned_points=plan.earned_points,
                    max_points=plan.max_points,
                    confirmed_by_user=plan.confirmed_by_user,
                )
                db.add(exam)
                db.commit()
                db.refresh(exam)
                exam_id = exam.id
                stats["exams_created"] += 1

            existing_hashes = set(
                db.scalars(
                    select(m.SchoolPaperAttachment.sha256).where(
                        m.SchoolPaperAttachment.school_exam_id == exam_id,
                        m.SchoolPaperAttachment.owner_id == owner,
                    )
                ).all()
            )
            for att in plan.attachments:
                if att.sha256 in existing_hashes:
                    stats["attachments_skipped"] += 1
                    continue
                data = att.path.read_bytes()
                save_school_paper(
                    db,
                    exam_id,
                    owner,
                    att.filename,
                    att.media_type,
                    data,
                    att.sha256,
                )
                existing_hashes.add(att.sha256)
                stats["attachments_uploaded"] += 1

    return stats


def _http_json(
    url: str,
    *,
    token: str,
    method: str = "GET",
    body: Any = None,
) -> Any:
    """使用标准库发起带 Admin Bearer 鉴权的 JSON 请求。"""
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"网络请求失败 {method} {url}: {exc}") from exc


def import_via_api(
    plans: list[PlannedExam],
    *,
    api_url: str,
    token: str,
    dry_run: bool = False,
) -> dict[str, int]:
    """经官方 Admin HTTP API 幂等创建学校考试并上传原件/答题卡附件。"""
    stats = {
        "exams_created": 0,
        "exams_existing": 0,
        "attachments_uploaded": 0,
        "attachments_skipped": 0,
    }
    if dry_run:
        return stats

    base = api_url.rstrip("/")
    # 先校验管理令牌有效性
    _http_json(f"{base}/api/admin/verify", token=token, method="GET")

    for plan in plans:
        existing_list = _http_json(
            f"{base}/api/school-exams?{urlencode({'subject': plan.subject})}",
            token=token,
            method="GET",
        )
        matched = next(
            (
                row
                for row in existing_list
                if row["title"] == plan.title and row["exam_date"] == plan.exam_date
            ),
            None,
        )
        if matched is not None:
            exam_id = matched["id"]
            stats["exams_existing"] += 1
        else:
            created = _http_json(
                f"{base}/api/school-exams",
                token=token,
                method="POST",
                body={
                    "subject": plan.subject,
                    "title": plan.title,
                    "exam_date": plan.exam_date,
                    "earned_points": plan.earned_points,
                    "max_points": plan.max_points,
                    "confirmed_by_user": plan.confirmed_by_user,
                },
            )
            exam_id = created["id"]
            stats["exams_created"] += 1

        detail = _http_json(f"{base}/api/school-exams/{exam_id}", token=token, method="GET")
        existing_hashes = {att["sha256"] for att in detail.get("attachments", [])}
        for att in plan.attachments:
            if att.sha256 in existing_hashes:
                stats["attachments_skipped"] += 1
                continue
            qs = urlencode({"filename": att.filename, "expected_sha256": att.sha256})
            req = Request(
                f"{base}/api/school-exams/{exam_id}/paper?{qs}",
                data=att.path.read_bytes(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": att.media_type,
                },
                method="POST",
            )
            try:
                with urlopen(req, timeout=120) as resp:
                    _ = resp.read()
            except HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"上传失败 {att.filename} (HTTP {exc.code}): {err_body}") from exc
            existing_hashes.add(att.sha256)
            stats["attachments_uploaded"] += 1

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="学校考试原卷与答题卡目录幂等导入工具")
    parser.add_argument("--dir", type=Path, help="包含各科试卷与答题卡文件的目录路径")
    parser.add_argument("--manifest", type=Path, help="可选外部 JSON 清单文件路径（与 --dir 二选一）")
    parser.add_argument("--title-prefix", default="", help="考试名称前缀（默认使用目录名）")
    parser.add_argument("--exam-date", default="2026-10-15", help="考试日期 YYYY-MM-DD（默认 2026-10-15）")
    parser.add_argument("--max-points", default="", help="各科满分映射，如 math=100,physics=70,chinese=100,ethics=50")
    parser.add_argument("--earned-points", default="", help="各科实得总分映射（默认 0）")
    parser.add_argument("--confirmed", action="store_true", help="创建时直接标记为已人工核对总分（默认 false 待确认）")
    parser.add_argument("--api-url", default="", help="目标服务根地址（如 http://127.0.0.1:8180）")
    parser.add_argument("--token", default="", help="Admin Bearer Token（未传时读取 SHUTONG_ADMIN_TOKEN）")
    parser.add_argument("--direct", action="store_true", help="离线直连数据库与私有附件目录")
    parser.add_argument("--db-url", default="", help="--direct 模式下显式指定数据库连接字符串")
    parser.add_argument("--dry-run", action="store_true", help="仅预览计划与哈希，不执行写入")
    args = parser.parse_args(argv)

    if not args.manifest and not args.dir:
        parser.error("必须提供 --dir 或 --manifest")
    if args.manifest:
        plans = build_plan_from_manifest(args.manifest)
    else:
        title_prefix = args.title_prefix.strip() or args.dir.name
        plans = build_plan_from_dir(
            args.dir,
            title_prefix=title_prefix,
            exam_date=args.exam_date,
            max_points_map=parse_points_map(args.max_points),
            earned_points_map=parse_points_map(args.earned_points),
            confirmed_by_user=args.confirmed,
        )

    if not plans:
        print("未在目录中识别到可导入的校考文件。")
        return 1

    print(f"已规划 {len(plans)} 场学校考试：")
    for plan in plans:
        status = "已核对" if plan.confirmed_by_user else "待核对"
        print(f"  • [{plan.subject}] {plan.title} ({plan.exam_date}) {plan.earned_points}/{plan.max_points} [{status}]")
        for att in plan.attachments:
            print(f"      - {att.filename} ({att.byte_size} bytes, sha256={att.sha256[:16]}...)")

    if args.dry_run:
        print("DRY-RUN 预览结束：未写入数据库与附件目录。")
        return 0

    if args.api_url:
        token = args.token or os.getenv("SHUTONG_ADMIN_TOKEN", "")
        if not token:
            raise SystemExit("使用 --api-url 时必须提供 --token 或环境变量 SHUTONG_ADMIN_TOKEN")
        stats = import_via_api(plans, api_url=args.api_url, token=token, dry_run=False)
    elif args.direct:
        stats = import_via_direct(plans, db_url=args.db_url or None, dry_run=False)
    else:
        raise SystemExit("请指定 --api-url <url> 或 --direct（或加 --dry-run 仅预览）")

    print(
        f"导入完成：新建考试 {stats['exams_created']} 场，复用已有考试 {stats['exams_existing']} 场；"
        f"新传附件 {stats['attachments_uploaded']} 份，跳过已存在附件 {stats['attachments_skipped']} 份。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
