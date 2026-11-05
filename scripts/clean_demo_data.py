#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全、原子、幂等的虚构演示数据清理工具。
严格依据外键约束顺序自底向上级联删除演示题源及关联的题目、版本、曝光与作答记录。
绝不执行 TRUNCATE、DROP TABLE 或全局非条件删除。

用法：
    # 预览将删除的数据（不产生真实删除）
    uv run python scripts/clean_demo_data.py --dry-run
    
    # 确认执行删除（开发或生产环境）
    uv run python scripts/clean_demo_data.py --confirm
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from sqlalchemy import select, delete, or_
from shutong import models as m
from shutong.database import make_engine, sessionmaker

DEMO_KEYWORDS = ["虚构", "演示", "iPad 真机公式验收题源"]


def clean_demo_data(dry_run: bool = True, db_url: str | None = None) -> dict[str, int]:
    engine = make_engine(db_url)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    counts = {
        "sources": 0,
        "questions": 0,
        "question_versions": 0,
        "question_knowledge_links": 0,
        "exposures": 0,
        "answer_attempts": 0,
        "source_reviews": 0,
        "source_attachments": 0,
    }

    with Session() as session:
        # 1. 查找所有演示题源
        query_conditions = [m.SourceDocument.title.like(f"%{kw}%") for kw in DEMO_KEYWORDS]
        demo_sources = session.scalars(select(m.SourceDocument).where(or_(*query_conditions))).all()
        demo_source_ids = [s.id for s in demo_sources]
        counts["sources"] = len(demo_source_ids)

        if not demo_source_ids:
            print("ℹ️ 未在数据库中发现任何虚构演示题源，数据库状态纯净，无需清理。")
            return counts

        # 2. 查找关联的题目与版本
        demo_questions = session.scalars(select(m.Question).where(m.Question.source_document_id.in_(demo_source_ids))).all()
        demo_question_ids = [q.id for q in demo_questions]
        counts["questions"] = len(demo_question_ids)

        demo_versions = session.scalars(select(m.QuestionVersion).where(m.QuestionVersion.question_id.in_(demo_question_ids))).all() if demo_question_ids else []
        demo_version_ids = [v.id for v in demo_versions]
        counts["question_versions"] = len(demo_version_ids)

        # 3. 查找关联的曝光与作答
        demo_exposures = session.scalars(select(m.Exposure).where(m.Exposure.question_id.in_(demo_question_ids))).all() if demo_question_ids else []
        demo_exposure_ids = [e.id for e in demo_exposures]
        counts["exposures"] = len(demo_exposure_ids)

        demo_attempts = session.scalars(select(m.AnswerAttempt).where(m.AnswerAttempt.exposure_id.in_(demo_exposure_ids))).all() if demo_exposure_ids else []
        demo_attempt_ids = [a.id for a in demo_attempts]
        counts["answer_attempts"] = len(demo_attempt_ids)

        # 4. 查找关联的知识点链接与导入记录
        demo_links = session.scalars(select(m.QuestionKnowledgeLink).where(m.QuestionKnowledgeLink.question_version_id.in_(demo_version_ids))).all() if demo_version_ids else []
        counts["question_knowledge_links"] = len(demo_links)

        demo_imported = session.scalars(select(m.ImportedQuestion).where(m.ImportedQuestion.question_version_id.in_(demo_version_ids))).all() if demo_version_ids else []
        counts["imported_questions"] = len(demo_imported)

        # 5. 查找审核记录与附件
        demo_reviews = session.scalars(select(m.SourceReview).where(m.SourceReview.source_document_id.in_(demo_source_ids))).all()
        counts["source_reviews"] = len(demo_reviews)

        demo_attachments = session.scalars(select(m.SourceAttachment).where(m.SourceAttachment.source_document_id.in_(demo_source_ids))).all()
        counts["source_attachments"] = len(demo_attachments)

        print("--------------------------------------------------")
        print("发现待清理的演示数据清单：")
        print(f"  • 演示题源 (SourceDocument):         {counts['sources']} 个")
        print(f"  • 演示题目 (Question):               {counts['questions']} 道")
        print(f"  • 题目版本 (QuestionVersion):        {counts['question_versions']} 个")
        print(f"  • 知识点关联 (QuestionKnowledgeLink): {counts['question_knowledge_links']} 条")
        print(f"  • 题目导入关联 (ImportedQuestion):    {counts['imported_questions']} 条")
        print(f"  • 演示答题记录 (AnswerAttempt):       {counts['answer_attempts']} 条")
        print(f"  • 演示曝光记录 (Exposure):            {counts['exposures']} 条")
        print(f"  • 来源审核记录 (SourceReview):        {counts['source_reviews']} 条")
        print(f"  • 来源附件记录 (SourceAttachment):    {counts['source_attachments']} 条")
        print("--------------------------------------------------")

        if dry_run:
            print("🔍 当前为 --dry-run 模式，未执行真实数据库删除。")
            return counts

        # 执行自底向上物理删除（单事务内）
        print("⚡ 正在执行原子清理...")
        if demo_attempt_ids:
            session.execute(delete(m.AnswerAttempt).where(m.AnswerAttempt.id.in_(demo_attempt_ids)))
        if demo_exposure_ids:
            session.execute(delete(m.Exposure).where(m.Exposure.id.in_(demo_exposure_ids)))
        if demo_version_ids:
            session.execute(delete(m.QuestionKnowledgeLink).where(m.QuestionKnowledgeLink.question_version_id.in_(demo_version_ids)))
            session.execute(delete(m.ImportedQuestion).where(m.ImportedQuestion.question_version_id.in_(demo_version_ids)))
            session.execute(delete(m.QuestionVersion).where(m.QuestionVersion.id.in_(demo_version_ids)))
        if demo_question_ids:
            session.execute(delete(m.Question).where(m.Question.id.in_(demo_question_ids)))
        if demo_source_ids:
            session.execute(delete(m.SourceReview).where(m.SourceReview.source_document_id.in_(demo_source_ids)))
            session.execute(delete(m.SourceAttachment).where(m.SourceAttachment.source_document_id.in_(demo_source_ids)))
            session.execute(delete(m.SourceDocument).where(m.SourceDocument.id.in_(demo_source_ids)))

        session.commit()
        print("✅ 演示数据清理完毕，事务已成功提交。")

    return counts


def main():
    parser = argparse.ArgumentParser(description="安全清理虚构演示数据工具")
    parser.add_argument("--dry-run", action="store_true", help="预览将被删除的记录，不进行真实删除")
    parser.add_argument("--confirm", action="store_true", help="显式确认并执行删除")
    parser.add_argument("--database-url", type=str, default=None, help="目标数据库连接串，缺省读取 DATABASE_URL 或开发库")

    args = parser.parse_args()

    if not args.dry_run and not args.confirm:
        print("⚠️ 请指定 --dry-run（预览）或 --confirm（确认执行删除）")
        sys.exit(1)

    clean_demo_data(dry_run=not args.confirm, db_url=args.database_url)


if __name__ == "__main__":
    main()
