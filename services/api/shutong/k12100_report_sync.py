"""k12100「总分」分析报告册下载与档案补全后台任务。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import k12100_backfill as backfill
from . import models as m
from . import private_files as files
from . import school_report_pipeline as report_pipeline
from .home import build_school_exam_archive_dir_name, resolve_repo_root


class _BrowserInterruptedWithPartial(RuntimeError):
    """浏览器下载批次中途停止，但本地已持久化保存了至少 1 份有效报告。"""

    def __init__(self, code: str, message: str, partial_bundle: dict[str, Any]) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.partial_bundle = partial_bundle


def _read_partial_bundle(out_path: Path, *, download_dir: Path) -> dict[str, Any] | None:
    if not out_path.is_file():
        return None
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    raw_downloads = payload.get("downloads")
    if not isinstance(raw_downloads, list) or not raw_downloads:
        return None
    valid_downloads = [
        item
        for item in raw_downloads
        if isinstance(item, dict) and _safe_downloaded_file(item.get("file"), allowed_root=download_dir) is not None
    ]
    if not valid_downloads:
        return None
    return {
        "status": "collected",
        "home_exams": payload.get("home_exams") if isinstance(payload.get("home_exams"), list) else [],
        "downloads": valid_downloads,
        "failures": payload.get("failures") if isinstance(payload.get("failures"), list) else [],
    }


def _download_reports_with_browser(
    *,
    config_dir: Path,
    creds: dict[str, str],
    skip_exam_ids: set[str],
    skip_identities: list[dict[str, Any]] | None = None,
    max_exams: int,
    headless: bool,
    download_dir: Path,
    exam_keyword: str = "",
    exam_date: str = "",
    external_exam_id: str = "",
) -> dict[str, Any]:
    """调用宿主机 Playwright 下载 k12100 首页未同步场次的「总分」分析报告册 PDF。"""
    node_bin = backfill._find_node_binary()  # noqa: SLF001
    if not node_bin:
        raise RuntimeError("K12100_LOCAL_RUNNER_UNAVAILABLE: 未找到宿主 Node.js")
    repo_root = resolve_repo_root(__file__)
    script_path = repo_root / "scripts" / "k12100_browser.mjs"
    if not script_path.is_file():
        raise RuntimeError("K12100_LOCAL_RUNNER_UNAVAILABLE: 缺少 scripts/k12100_browser.mjs")

    skip_path = download_dir / "skip.json"
    out_path = download_dir / "report_downloads.json"
    skip_path.write_text(
        json.dumps(
            {
                "external_exam_ids": sorted(skip_exam_ids),
                "complete_identities": list(skip_identities or []),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(skip_path, 0o600)
    except OSError:
        pass

    cmd = [
        node_bin,
        str(script_path),
        "--mode",
        "reports",
        "--profile-dir",
        str(config_dir / "k12100-browser-profile"),
        "--skip-file",
        str(skip_path),
        "--download-dir",
        str(download_dir),
        "--output",
        str(out_path),
        "--max-exams",
        str(backfill.clamp_max_exams(max_exams)),
        "--headless" if headless else "--headed",
    ]
    if exam_keyword.strip():
        cmd.extend(["--exam-keyword", exam_keyword.strip()])
    if exam_date.strip():
        cmd.extend(["--exam-date", exam_date.strip()])
    if external_exam_id.strip():
        cmd.extend(["--external-exam-id", external_exam_id.strip()])

    child_env = os.environ.copy()
    child_env["K12100_USERNAME"] = creds["K12100_USERNAME"]
    child_env["K12100_PASSWORD"] = creds["K12100_PASSWORD"]

    try:
        res = subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=child_env,
            capture_output=True,
            text=True,
            timeout=420,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial = _read_partial_bundle(out_path, download_dir=download_dir)
        msg = "下载报告超时已停止"
        if partial is not None:
            raise _BrowserInterruptedWithPartial("K12100_BROWSER_FAILED", msg, partial) from exc
        raise RuntimeError("K12100_BROWSER_FAILED: 浏览器下载分析报告超时，请重试或改用报告导入 Tab 本地扫描。") from exc

    err_pair: tuple[str, str] | None = None
    if res.returncode == 2:
        err_pair = ("K12100_LOGIN_REQUIRED", "会话已失效或自动登录未完成，请勾选可见窗口重新登录后再试。")
    elif res.returncode == 3:
        err_pair = ("K12100_CIRCUIT_BREAKER", "检测到验证码或频控（401/403/429），已立即熔断并停止下载。")
    elif res.returncode != 0 or not out_path.is_file():
        err_pair = ("K12100_BROWSER_FAILED", "浏览器下载分析报告中断，可重新点击同步继续下载剩余场次。")

    if err_pair is not None:
        code, message = err_pair
        partial = _read_partial_bundle(out_path, download_dir=download_dir)
        if partial is not None:
            raise _BrowserInterruptedWithPartial(code, message, partial)
        raise RuntimeError(f"{code}: {message}")

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("K12100_INVALID_BUNDLE: 报告下载摘要结构无效。")
    return payload


def _safe_downloaded_file(raw_path: Any, *, allowed_root: Path | None) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    candidate = Path(raw_path)
    if candidate.is_symlink() or not candidate.is_file():
        return None
    if allowed_root is not None:
        try:
            candidate.resolve().relative_to(allowed_root.resolve())
        except (ValueError, OSError):
            return None
    return candidate


def process_downloaded_reports(
    db: Session,
    *,
    owner: str,
    bundle: dict[str, Any],
    allowed_root: Path | None = None,
    auto_map_fn: Callable[[Session, m.SchoolExamReport], int] | None = None,
    progress_cb: Callable[[str], None] | None = None,
    archive_exam_id: str | None = None,
) -> dict[str, Any]:
    """解析已下载的 k12100 总分报告，执行新建/更新/补全/草稿与答题卡同步。"""
    status = str(bundle.get("status") or "")
    if status == "login_required":
        raise RuntimeError(f"K12100_LOGIN_REQUIRED: {bundle.get('reason') or '会话已失效'}")
    if status == "circuit_breaker":
        raise RuntimeError(f"K12100_CIRCUIT_BREAKER: {bundle.get('reason') or '触发熔断'}")

    home_exams_raw = bundle.get("home_exams") if isinstance(bundle.get("home_exams"), list) else []
    home_exams: list[dict[str, Any]] = [
        {
            "external_exam_id": str(item.get("external_exam_id") or ""),
            "exam_name": str(item.get("exam_name") or ""),
            "exam_date": str(item.get("exam_date") or ""),
            "grade": str(item.get("grade") or ""),
            "academic_year": str(item.get("academic_year") or ""),
            "exam_type": str(item.get("exam_type") or ""),
            "already_synced": bool(item.get("already_synced")),
            "matched_report_id": str(item.get("matched_report_id") or "") or None,
        }
        for item in home_exams_raw
        if isinstance(item, dict)
    ]

    # 对按身份命中已有完整本地报告、但仅缺平台 external_exam_id/exam_date 的场次，直接静默回填
    for hx in home_exams:
        rep_id = hx.get("matched_report_id")
        ext_id = hx.get("external_exam_id") or ""
        if not rep_id or not ext_id:
            continue
        rep = db.get(m.SchoolExamReport, rep_id)
        if rep is None or rep.learner_id != owner:
            continue
        changed = False
        if not rep.external_exam_id:
            conflict = db.execute(
                select(m.SchoolExamReport.id).where(
                    m.SchoolExamReport.learner_id == owner,
                    m.SchoolExamReport.external_exam_id == ext_id,
                    m.SchoolExamReport.id != rep.id,
                )
            ).first()
            if conflict is None:
                rep.external_exam_id = ext_id[:80]
                changed = True
        norm_date_str, _ = report_pipeline._parse_k12100_exam_date(hx.get("exam_date"))  # noqa: SLF001
        if norm_date_str and not rep.exam_date:
            rep.exam_date = norm_date_str
            changed = True
        if changed:
            report_pipeline.match_report(db, report=rep)
            db.flush()

    downloads = bundle.get("downloads") if isinstance(bundle.get("downloads"), list) else []
    failures: list[dict[str, Any]] = [
        dict(entry) for entry in (bundle.get("failures") or []) if isinstance(entry, dict)
    ]

    reports_out: list[dict[str, Any]] = []
    subject_actions: list[dict[str, Any]] = []
    totals = {
        "home_exams": len(home_exams),
        "skipped_existing": sum(1 for item in home_exams if item["already_synced"]),
        "downloaded": len(downloads),
        "reports_registered": 0,
        "created_exams": 0,
        "updated_exams": 0,
        "filled_exams": 0,
        "unchanged_exams": 0,
        "locked_conflicts": 0,
        "identity_conflicts": 0,
        "awaiting_exam_date": 0,
        "ambiguous_exams": 0,
        "drafts_created": 0,
        "drafts_updated": 0,
        "auto_mapped": 0,
        "cards_created": 0,
        "cards_synced": 0,
        "ranks_synced": 0,
        "failures": len(failures),
    }

    for index, item in enumerate(downloads, start=1):
        if not isinstance(item, dict):
            continue
        ext_id = str(item.get("external_exam_id") or "").strip()
        exam_name = str(item.get("exam_name") or "").strip()
        if progress_cb:
            progress_cb(f"正在解析第 {index}/{len(downloads)} 份报告（{exam_name or ext_id or '校考'}）并更新档案…")

        file_path = _safe_downloaded_file(item.get("file"), allowed_root=allowed_root)
        if file_path is None:
            failures.append(
                {
                    "external_exam_id": ext_id,
                    "exam_name": exam_name,
                    "code": "K12100_REPORT_FILE_MISSING",
                    "reason": "下载文件不存在或不在安全临时目录内",
                }
            )
            totals["failures"] += 1
            continue

        data = file_path.read_bytes()
        try:
            files.validate_file(data, "application/pdf")
        except HTTPException as exc:
            failures.append(
                {
                    "external_exam_id": ext_id,
                    "exam_name": exam_name,
                    "code": "K12100_REPORT_NOT_PDF",
                    "reason": f"PDF 校验未通过：{exc.detail}",
                }
            )
            totals["failures"] += 1
            continue

        platform_meta = {
            "external_exam_id": ext_id,
            "exam_date": item.get("exam_date"),
            "exam_name": exam_name,
            "grade": item.get("grade"),
            "academic_year": item.get("academic_year"),
            "exam_type": item.get("exam_type"),
        }
        suggested_name = str(item.get("suggested_filename") or f"{exam_name or '校考'}_分析报告册.pdf")
        try:
            report, _created_report = report_pipeline.register_report_bytes(
                db,
                owner=owner,
                data=data,
                filename=suggested_name,
                media_type="application/pdf",
                source_ref=f"k12100/{ext_id or report_pipeline.sha256(data).hexdigest()[:12]}",
                platform_meta=platform_meta,
            )
        except Exception as exc:
            failures.append(
                {
                    "external_exam_id": ext_id,
                    "exam_name": exam_name,
                    "code": "K12100_REPORT_PARSE_FAILED",
                    "reason": str(exc)[:180] or "分析报告册解析失败",
                }
            )
            totals["failures"] += 1
            continue

        target_archive_dir: str | None = None
        if archive_exam_id:
            target_exam = db.get(m.SchoolExam, archive_exam_id)
            if target_exam is not None and target_exam.learner_id == owner:
                if not target_exam.archive_dir:
                    target_exam.archive_dir = build_school_exam_archive_dir_name(
                        target_exam.exam_date, target_exam.title, target_exam.id
                    )
                    db.flush()
                files.ensure_school_exam_archive_dirs(target_exam.archive_dir)
                target_archive_dir = target_exam.archive_dir

        upsert = report_pipeline.upsert_exams_from_report(
            db,
            report=report,
            platform_meta=platform_meta,
            archive_dir=target_archive_dir,
            allow_create=archive_exam_id is None,
            archive_exam_id=archive_exam_id,
        )
        db.commit()
        db.refresh(report)

        drafts = report_pipeline.generate_item_drafts(db, report=report, update_unconfirmed_drafts=True)
        auto_mapped = auto_map_fn(db, report) if auto_map_fn else 0
        if auto_mapped:
            db.commit()

        cards_created = 0
        cards_synced = 0
        if report.answer_card_pages:
            try:
                cards = report_pipeline.build_answer_card_attachments(
                    db,
                    report=report,
                    rotation=0,
                    archive_dir=target_archive_dir,
                )
                cards_created = int(cards.get("created") or 0)
                cards_synced = int(cards.get("ledger_synced") or 0)
            except HTTPException:
                pass

        counts = upsert["counts"]
        totals["reports_registered"] += 1
        totals["created_exams"] += counts["created"]
        totals["updated_exams"] += counts["updated"]
        totals["filled_exams"] += counts["filled"]
        totals["unchanged_exams"] += counts["unchanged"]
        totals["locked_conflicts"] += counts["locked_conflict"]
        totals["identity_conflicts"] += counts["identity_conflict"]
        totals["awaiting_exam_date"] += counts["awaiting_exam_date"]
        totals["ambiguous_exams"] += counts["ambiguous"]
        totals["drafts_created"] += int(drafts.get("created") or 0)
        totals["drafts_updated"] += int(drafts.get("updated") or 0)
        totals["auto_mapped"] += int(auto_mapped or 0)
        totals["cards_created"] += cards_created
        totals["cards_synced"] += cards_synced
        totals["ranks_synced"] += int(upsert.get("ranks_synced") or 0)

        for row in upsert["actions"]:
            subject_actions.append(
                {
                    **row,
                    "report_id": report.id,
                    "report_title": report.title or exam_name or report.filename,
                    "external_exam_id": report.external_exam_id,
                    "report_exam_date": report.exam_date,
                    "academic_year": report.academic_year,
                    "grade": report.grade,
                    "exam_type": report.exam_type,
                }
            )

        reports_out.append(
            {
                "report_id": report.id,
                "title": report.title or exam_name,
                "external_exam_id": report.external_exam_id,
                "exam_date": report.exam_date,
                "academic_year": report.academic_year,
                "grade": report.grade,
                "exam_type": report.exam_type,
                "match_state": report.match_state,
                "counts": counts,
                "drafts_created": int(drafts.get("created") or 0),
                "drafts_updated": int(drafts.get("updated") or 0),
                "cards_synced": cards_synced,
            }
        )

    return {
        "home_exams": home_exams,
        "reports": reports_out,
        "subject_actions": subject_actions,
        "totals": totals,
        "failures": failures,
        "knowledge_evidence_created": 0,
    }


def start_k12100_report_job(
    db: Session,
    *,
    owner: str,
    auto_map_fn: Callable[[Session, m.SchoolExamReport], int],
    max_exams: int = 3,
    headless: bool = False,
    archive_exam_id: str | None = None,
) -> dict[str, Any]:
    """启动单实例 k12100「总分」报告下载与档案补全任务（与旧同步任务共用互斥锁）。"""

    def _worker(job_id: str, cfg_dir: Path, creds: dict[str, str], session_factory: sessionmaker[Session]) -> None:
        backfill._update_job(  # noqa: SLF001
            job_id,
            state="collecting",
            progress_percent=15,
            stage_message="下载前先核对本地已存考试完整性（合并重复记录、从本地 PDF 补全排名与最高分）…",
        )
        target_exam_keyword = ""
        target_exam_date = ""
        target_external_exam_id = ""
        with session_factory() as query_db:
            hydrated = report_pipeline.hydrate_incomplete_local_reports(
                query_db,
                owner=owner,
                auto_map_fn=auto_map_fn,
            )
            skip_summary = report_pipeline.collect_complete_skip_targets(query_db, owner=owner)
            if archive_exam_id:
                target_exam = query_db.get(m.SchoolExam, archive_exam_id)
                if target_exam is not None and target_exam.learner_id == owner:
                    target_exam_keyword = str(target_exam.series_title or target_exam.title or "").strip()
                    target_exam_date = str(target_exam.exam_date or "").strip()
                    target_external_exam_id = str(target_exam.external_exam_id or "").strip()
                    if not target_exam_keyword:
                        paper_row = query_db.execute(
                            select(m.SchoolExamPaper).where(
                                m.SchoolExamPaper.owner_id == owner,
                                m.SchoolExamPaper.school_exam_id == archive_exam_id,
                            )
                        ).scalars().first()
                        if paper_row is not None and paper_row.exam_name:
                            target_exam_keyword = str(paper_row.exam_name).strip()

        existing_ids = set(skip_summary["complete_external_exam_ids"])
        complete_identities = skip_summary["complete_identities"]

        backfill._update_job(  # noqa: SLF001
            job_id,
            state="collecting",
            progress_percent=35,
            stage_message=(
                f"已完成本地核对；正在登录 k12100 定向查找「{target_exam_keyword}」总分报告…"
                if target_exam_keyword
                else f"已完成本地核对（{len(existing_ids)} 场已完整）；正在登录 k12100 首页排查是否有新增或未完整场次…"
            ),
        )
        with TemporaryDirectory(prefix="shutong-k12100-reports-") as tmpdir:
            download_dir = Path(tmpdir)
            try:
                os.chmod(download_dir, 0o700)
            except OSError:
                pass
            try:
                bundle = _download_reports_with_browser(
                    config_dir=cfg_dir,
                    creds=creds,
                    skip_exam_ids=existing_ids,
                    skip_identities=complete_identities,
                    max_exams=backfill.clamp_max_exams(max_exams),
                    headless=headless,
                    download_dir=download_dir,
                    exam_keyword=target_exam_keyword,
                    exam_date=target_exam_date,
                    external_exam_id=target_external_exam_id,
                )
            except _BrowserInterruptedWithPartial as partial_exc:
                backfill._update_job(  # noqa: SLF001
                    job_id,
                    state="backfilling",
                    progress_percent=70,
                    stage_message="下载中途停止，正在将此前已下完的报告入库…",
                )
                with session_factory() as worker_db:
                    partial_result = process_downloaded_reports(
                        worker_db,
                        owner=owner,
                        bundle=partial_exc.partial_bundle,
                        allowed_root=download_dir,
                        auto_map_fn=auto_map_fn,
                        progress_cb=lambda msg: backfill._update_job(job_id, progress_percent=85, stage_message=msg),  # noqa: SLF001
                        archive_exam_id=archive_exam_id,
                    )
                    worker_db.commit()
                p_totals = partial_result["totals"]
                partial_msg = (
                    f"{partial_exc.message} 已保留入库此前下完的 {p_totals['reports_registered']} 份报告"
                    f"（新建 {p_totals['created_exams']} 科、更新 {p_totals['updated_exams']} 科、补全 {p_totals['filled_exams']} 科）。"
                )
                backfill._update_job(  # noqa: SLF001
                    job_id,
                    state="failed",
                    progress_percent=100,
                    stage_message=partial_msg,
                    error_code=partial_exc.code,
                    error_message=partial_msg,
                    report_result=partial_result,
                )
                return

            backfill._update_job(  # noqa: SLF001
                job_id,
                state="backfilling",
                progress_percent=70,
                stage_message="报告下载完成，正在解析全科成绩、更新考试档案与待核对草稿…",
            )
            with session_factory() as worker_db:
                result = process_downloaded_reports(
                    worker_db,
                    owner=owner,
                    bundle=bundle,
                    allowed_root=download_dir,
                    auto_map_fn=auto_map_fn,
                    progress_cb=lambda msg: backfill._update_job(job_id, progress_percent=85, stage_message=msg),  # noqa: SLF001
                    archive_exam_id=archive_exam_id,
                )
                worker_db.commit()

        result["local_hydrated"] = hydrated
        totals = result["totals"]
        if totals["downloaded"] == 0 and totals["failures"] == 0:
            summary = f"核对完成：k12100 首页共 {totals['home_exams']} 场考试，全部已有完整同步记录，未执行重复下载。"
        elif totals["downloaded"] == 0 and totals["failures"] > 0:
            summary = result["failures"][0].get("reason") or "未找到匹配的考试场次。"
        else:
            summary = (
                f"报告同步完成：下载 {totals['downloaded']} 份，更新 {totals['updated_exams']} 科、补全 {totals['filled_exams']} 科、"
                f"同步排名 {totals.get('ranks_synced', 0)} 条、"
                f"新增草稿 {totals['drafts_created']} 题、更新草稿 {totals['drafts_updated']} 题。"
            )
        backfill._update_job(  # noqa: SLF001
            job_id,
            state="completed",
            progress_percent=100,
            stage_message=summary,
            report_result=result,
        )

    return backfill.launch_k12100_job(
        db,
        kind="report",
        initial_stage_message="任务已创建，准备登录 k12100 下载「总分」分析报告…",
        extra_fields=None,
        worker_fn=_worker,
    )
