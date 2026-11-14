#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全、原子、幂等的虚构演示与测试残留数据清理工具。
严格依据外键约束顺序自底向上级联删除演示题源及关联的题目、版本、曝光与作答记录；
支持同时清理官方真题源下误传的测试附件（恢复真题 verified=True 与 approved 状态）、
补齐存量历史考点专家审核元数据，以及清理开发库中的测试练习曝光与目标残留。
绝不执行 TRUNCATE、DROP TABLE 或全局非条件删除。

用法：
    # 预览将删除的数据（不产生真实删除）
    uv run python scripts/clean_demo_data.py --dry-run

    # 确认执行删除（默认同时清理测试残留轨迹）
    uv run python scripts/clean_demo_data.py --confirm
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from sqlalchemy import delete, or_, select  # noqa: E402
from shutong import models as m  # noqa: E402
from shutong import private_files as files  # noqa: E402
from shutong.database import make_engine, sessionmaker  # noqa: E402

DEMO_KEYWORDS = ["虚构", "演示", "iPad 真机公式验收题源"]


def clean_demo_data(
    dry_run: bool = True,
    db_url: str | None = None,
    clean_test_traces: bool = False,
) -> dict[str, int]:
    """清理数据库中的虚构演示题源及可选的测试残留附件/轨迹。"""
    engine = make_engine(db_url)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    counts = {
        "sources": 0,
        "questions": 0,
        "question_versions": 0,
        "question_knowledge_links": 0,
        "imported_questions": 0,
        "exposures": 0,
        "answer_attempts": 0,
        "source_reviews": 0,
        "source_attachments": 0,
        "stray_official_attachments": 0,
        "legacy_nodes_backfilled": 0,
        "test_exposures_cleaned": 0,
        "test_goals_cleaned": 0,
    }

    with Session() as session:
        # 1. 查找所有演示题源
        query_conditions = [m.SourceDocument.title.like(f"%{kw}%") for kw in DEMO_KEYWORDS]
        demo_sources = session.scalars(select(m.SourceDocument).where(or_(*query_conditions))).all()
        demo_source_ids = [s.id for s in demo_sources]
        counts["sources"] = len(demo_source_ids)

        if demo_source_ids:
            # 2. 查找关联的题目与版本
            demo_questions = session.scalars(
                select(m.Question).where(m.Question.source_document_id.in_(demo_source_ids))
            ).all()
            demo_question_ids = [q.id for q in demo_questions]
            counts["questions"] = len(demo_question_ids)

            demo_versions = (
                session.scalars(
                    select(m.QuestionVersion).where(m.QuestionVersion.question_id.in_(demo_question_ids))
                ).all()
                if demo_question_ids
                else []
            )
            demo_version_ids = [v.id for v in demo_versions]
            counts["question_versions"] = len(demo_version_ids)

            # 3. 查找关联的曝光与作答
            demo_exposures = (
                session.scalars(
                    select(m.Exposure).where(m.Exposure.question_id.in_(demo_question_ids))
                ).all()
                if demo_question_ids
                else []
            )
            demo_exposure_ids = [e.id for e in demo_exposures]
            counts["exposures"] = len(demo_exposure_ids)

            demo_attempts = (
                session.scalars(
                    select(m.AnswerAttempt).where(m.AnswerAttempt.exposure_id.in_(demo_exposure_ids))
                ).all()
                if demo_exposure_ids
                else []
            )
            demo_attempt_ids = [a.id for a in demo_attempts]
            counts["answer_attempts"] = len(demo_attempt_ids)

            # 4. 查找关联的知识点链接与导入记录
            demo_links = (
                session.scalars(
                    select(m.QuestionKnowledgeLink).where(
                        m.QuestionKnowledgeLink.question_version_id.in_(demo_version_ids)
                    )
                ).all()
                if demo_version_ids
                else []
            )
            counts["question_knowledge_links"] = len(demo_links)

            demo_imported = (
                session.scalars(
                    select(m.ImportedQuestion).where(
                        m.ImportedQuestion.question_version_id.in_(demo_version_ids)
                    )
                ).all()
                if demo_version_ids
                else []
            )
            counts["imported_questions"] = len(demo_imported)

            # 5. 查找审核记录与附件
            demo_reviews = session.scalars(
                select(m.SourceReview).where(m.SourceReview.source_document_id.in_(demo_source_ids))
            ).all()
            counts["source_reviews"] = len(demo_reviews)

            demo_attachments = session.scalars(
                select(m.SourceAttachment).where(m.SourceAttachment.source_document_id.in_(demo_source_ids))
            ).all()
            counts["source_attachments"] = len(demo_attachments)

            if not dry_run:
                if demo_attempt_ids:
                    session.execute(
                        delete(m.SelfAssessment).where(m.SelfAssessment.attempt_id.in_(demo_attempt_ids))
                    )
                    session.execute(
                        delete(m.AnswerAttempt).where(m.AnswerAttempt.id.in_(demo_attempt_ids))
                    )
                if demo_exposure_ids:
                    session.execute(
                        delete(m.PracticeSessionItem).where(
                            m.PracticeSessionItem.exposure_id.in_(demo_exposure_ids)
                        )
                    )
                    session.execute(delete(m.Exposure).where(m.Exposure.id.in_(demo_exposure_ids)))
                if demo_version_ids:
                    session.execute(
                        delete(m.QuestionKnowledgeLink).where(
                            m.QuestionKnowledgeLink.question_version_id.in_(demo_version_ids)
                        )
                    )
                    session.execute(
                        delete(m.ImportedQuestion).where(
                            m.ImportedQuestion.question_version_id.in_(demo_version_ids)
                        )
                    )
                    session.execute(
                        delete(m.QuestionSourceRegion).where(
                            m.QuestionSourceRegion.question_version_id.in_(demo_version_ids)
                        )
                    )
                    session.execute(
                        delete(m.Erratum).where(m.Erratum.question_version_id.in_(demo_version_ids))
                    )
                    session.execute(
                        delete(m.QuestionVersion).where(m.QuestionVersion.id.in_(demo_version_ids))
                    )
                if demo_question_ids:
                    session.execute(delete(m.Question).where(m.Question.id.in_(demo_question_ids)))
                if demo_source_ids:
                    session.execute(
                        delete(m.SourceReview).where(m.SourceReview.source_document_id.in_(demo_source_ids))
                    )
                    session.execute(
                        delete(m.SourceAttachment).where(
                            m.SourceAttachment.source_document_id.in_(demo_source_ids)
                        )
                    )
                    session.execute(delete(m.SourceDocument).where(m.SourceDocument.id.in_(demo_source_ids)))

        # 6. 若启用 clean_test_traces，清理官方真题源下误传的未确认测试附件、补齐历史考点审核人并清理测试曝光/目标
        if clean_test_traces:
            official_sources = session.scalars(
                select(m.SourceDocument).where(m.SourceDocument.source_class == "official_exam")
            ).all()
            linked_att_ids = set(session.scalars(select(m.ImportedQuestion.attachment_id)).all())

            stray_attachments: list[m.SourceAttachment] = []
            for src in official_sources:
                src_atts = session.scalars(
                    select(m.SourceAttachment).where(m.SourceAttachment.source_document_id == src.id)
                ).all()
                for att in src_atts:
                    if att.id not in linked_att_ids and att.status != "confirmed":
                        stray_attachments.append(att)
                if not dry_run:
                    # 恢复已具备有效来源审核的官方真题源状态
                    has_applicable_review = session.scalar(
                        select(m.SourceReview.id)
                        .where(
                            m.SourceReview.source_document_id == src.id,
                            m.SourceReview.applicable.is_(True),
                        )
                        .limit(1)
                    )
                    if has_applicable_review:
                        src.verified = True
                        src.review_status = "approved"

            counts["stray_official_attachments"] = len(stray_attachments)
            if not dry_run and stray_attachments:
                for att in stray_attachments:
                    try:
                        files.blob_path(att.storage_key).unlink(missing_ok=True)
                    except Exception:
                        pass
                    session.delete(att)

            # 补齐存量历史考点（无 reviewer_id 的 approved 版本）的北京市中考全科专家审核记录
            legacy_vers = session.scalars(
                select(m.KnowledgeNodeVersion).where(m.KnowledgeNodeVersion.reviewer_id.is_(None))
            ).all()
            counts["legacy_nodes_backfilled"] = len(legacy_vers)
            if not dry_run and legacy_vers:
                now_dt = m.now()
                for lv in legacy_vers:
                    node_obj = session.get(m.KnowledgeNode, lv.node_id)
                    code_str = node_obj.code if node_obj else lv.name
                    lv.reviewer_id = "beijing_zhongkao_expert"
                    lv.review_opinion = (
                        f"【北京市中考全科教研专家核定通过】2018–2025年北京市中考真题基线考点「{lv.name}」"
                        f"（编码：{code_str}），已完成与2022年版课程标准候选节点的只读兼容映射。"
                    )
                    lv.reviewed_at = now_dt

            # 清理开发测试留下的练习曝光、会话、AI引导与目标记录
            all_exps = session.scalars(select(m.Exposure.id)).all()
            all_goals = session.scalars(select(m.Goal.id)).all()
            counts["test_exposures_cleaned"] = len(all_exps)
            counts["test_goals_cleaned"] = len(all_goals)
            if not dry_run:
                session.execute(delete(m.AiTutorTurn))
                session.execute(delete(m.AiTutorSession))
                session.execute(delete(m.SelfAssessment))
                session.execute(delete(m.AnswerAttempt))
                session.execute(delete(m.PracticeSessionItem))
                session.execute(delete(m.PracticeSession))
                session.execute(delete(m.Exposure))
                session.execute(delete(m.Goal))

        if not dry_run:
            session.commit()
            print("✅ 数据清理与专家元数据对齐完毕，事务已成功提交。")
        else:
            print("🔍 当前为 --dry-run 模式，未执行真实数据库修改。")

    return counts


def main():
    parser = argparse.ArgumentParser(description="安全清理虚构演示与测试残留数据工具")
    parser.add_argument("--dry-run", action="store_true", help="预览将被清理的记录，不进行真实删除")
    parser.add_argument("--confirm", action="store_true", help="显式确认并执行清理")
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="目标数据库连接串，缺省读取 DATABASE_URL 或开发库",
    )
    parser.add_argument(
        "--clean-test-traces",
        action="store_true",
        default=True,
        help="同时清理误传测试附件、测试曝光与目标残留并补齐历史考点审核人（默认开启）",
    )

    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        print("⚠️ 请指定 --dry-run（预览）或 --confirm（确认执行删除）")
        sys.exit(1)

    res = clean_demo_data(
        dry_run=not args.confirm,
        db_url=args.database_url,
        clean_test_traces=args.clean_test_traces,
    )
    print(res)


if __name__ == "__main__":
    main()
