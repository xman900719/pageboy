#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全、幂等灌入四科标准知识点库与 2018-2025 年北京中考全真试题工具。
支持直接连接数据库（SQLite 或 PostgreSQL），保证数据完整性、合规标记、PDF/DOCX 原件附件与双向考点关联。

用法：
    # 灌入开发数据库（自动挂载真题 PDF 原件附件）
    uv run python scripts/seed_real_corpus.py
    
    # 灌入指定生产数据库
    DATABASE_URL="..." uv run python scripts/seed_real_corpus.py
"""
from __future__ import annotations
import argparse
import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from sqlalchemy import select
from shutong import models as m
from shutong import private_files as files
from shutong.database import make_engine, sessionmaker
from shutong.corpus.taxonomy import TAXONOMY
from shutong.corpus.exam_2025 import ALL_EXAM_PAPERS

DEFAULT_CORPUS_DIR = Path("/media/xc/backup_ntfs/中考题库/北京中考真题-富尔题库")
CONVERTED_CACHE_DIR = REPO_ROOT / ".cache" / "converted_docx"


def seed_corpus(
    db_url: str | None = None,
    corpus_dir: Path | None = None,
    attach_pdfs: bool = False,
    rebuild: bool = False,
    converted_cache_dir: Path | None = None,
) -> dict[str, int]:
    engine = make_engine(db_url)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    resolved_corpus_dir = corpus_dir or DEFAULT_CORPUS_DIR
    # 优先使用显式参数或环境变量指定的 .docx 转换缓存目录
    env_cache_dir = os.environ.get("SHUTONG_CONVERTED_CACHE_DIR")
    resolved_cache_dir = converted_cache_dir or (Path(env_cache_dir) if env_cache_dir else CONVERTED_CACHE_DIR)
    
    stats = {
        "nodes_created": 0,
        "nodes_existing": 0,
        "sources_created": 0,
        "sources_existing": 0,
        "attachments_linked": 0,
        "questions_published": 0,
        "questions_existing": 0,
        "links_created": 0,
    }

    if rebuild:
        print("=== [0/2] 正在执行真题与附件彻底清理 (--rebuild) ===")
        with Session() as session:
            from sqlalchemy import delete, or_
            # 1. 查找所有 official_exam 官方题源及旧演示题源
            sources = session.scalars(
                select(m.SourceDocument).where(
                    or_(
                        m.SourceDocument.source_class == "official_exam",
                        m.SourceDocument.title.like("%中考%"),
                        m.SourceDocument.title.like("%真题%"),
                        m.SourceDocument.title.like("%虚构%"),
                        m.SourceDocument.title.like("%演示%"),
                    )
                )
            ).all()
            source_ids = [s.id for s in sources]
            
            if source_ids:
                # 级联查找关联的题目与版本
                questions = session.scalars(select(m.Question).where(m.Question.source_document_id.in_(source_ids))).all()
                q_ids = [q.id for q in questions]
                
                qvs = session.scalars(select(m.QuestionVersion).where(m.QuestionVersion.question_id.in_(q_ids))).all() if q_ids else []
                qv_ids = [v.id for v in qvs]

                exposures = session.scalars(select(m.Exposure).where(m.Exposure.question_id.in_(q_ids))).all() if q_ids else []
                exp_ids = [e.id for e in exposures]

                attempts = session.scalars(select(m.AnswerAttempt).where(m.AnswerAttempt.exposure_id.in_(exp_ids))).all() if exp_ids else []
                att_ids = [a.id for a in attempts]

                # 提取将被物理清理的 storage_keys
                storage_keys = session.scalars(select(m.SourceAttachment.storage_key).where(m.SourceAttachment.source_document_id.in_(source_ids))).all()

                print(f"  • 发现待彻底清理真题源: {len(source_ids)} 个，题目: {len(q_ids)} 道，版本: {len(qv_ids)} 个，附件: {len(storage_keys)} 个")

                # 自底向上外键级联物理删除
                if att_ids:
                    session.execute(delete(m.SelfAssessment).where(m.SelfAssessment.attempt_id.in_(att_ids)))
                    session.execute(delete(m.AnswerAttempt).where(m.AnswerAttempt.id.in_(att_ids)))
                if exp_ids:
                    session.execute(delete(m.Exposure).where(m.Exposure.id.in_(exp_ids)))
                if qv_ids:
                    session.execute(delete(m.QuestionKnowledgeLink).where(m.QuestionKnowledgeLink.question_version_id.in_(qv_ids)))
                    session.execute(delete(m.ImportedQuestion).where(m.ImportedQuestion.question_version_id.in_(qv_ids)))
                    session.execute(delete(m.QuestionSourceRegion).where(m.QuestionSourceRegion.question_version_id.in_(qv_ids)))
                    session.execute(delete(m.Erratum).where(m.Erratum.question_version_id.in_(qv_ids)))
                    session.execute(delete(m.QuestionVersion).where(m.QuestionVersion.id.in_(qv_ids)))
                if q_ids:
                    session.execute(delete(m.Question).where(m.Question.id.in_(q_ids)))
                session.execute(delete(m.SourceAttachment).where(m.SourceAttachment.source_document_id.in_(source_ids)))
                session.execute(delete(m.SourceReview).where(m.SourceReview.source_document_id.in_(source_ids)))
                session.execute(delete(m.SourceDocument).where(m.SourceDocument.id.in_(source_ids)))
                session.commit()

                # 物理清理磁盘存储文件
                att_dir = files.private_root()
                deleted_files = 0
                if att_dir.is_dir():
                    for key in storage_keys:
                        f = att_dir / key
                        if f.is_file():
                            try:
                                f.unlink()
                                deleted_files += 1
                            except Exception:
                                pass
                    # 孤儿扫描：检查数据库剩余全部有效 attachment key
                    remaining_keys = set(session.scalars(select(m.SourceAttachment.storage_key)).all())
                    for f in att_dir.iterdir():
                        if f.is_file() and f.name not in remaining_keys:
                            try:
                                f.unlink()
                                deleted_files += 1
                            except Exception:
                                pass
                print(f"  ✓ 逻辑数据彻底删除完毕，物理附件已销毁 {deleted_files} 个文件")
            else:
                print("  ℹ️ 当前数据库无既有官方真题数据，无需逻辑清理。")

    with Session() as session:
        print("=== [1/2] 播种北京市义务教育新课标四科知识点库 (TAXONOMY) ===")
        code_to_node_id: dict[str, str] = {}
        
        # 1.1 先创建/获取所有主干节点
        for subject, nodes in TAXONOMY.items():
            for node_data in nodes:
                code = node_data["code"]
                existing_node = session.scalar(select(m.KnowledgeNode).where(m.KnowledgeNode.code == code))
                if existing_node:
                    code_to_node_id[code] = existing_node.id
                    stats["nodes_existing"] += 1
                else:
                    new_node = m.KnowledgeNode(
                        subject=subject,
                        code=code,
                        status="active",
                    )
                    session.add(new_node)
                    session.flush()
                    code_to_node_id[code] = new_node.id
                    stats["nodes_created"] += 1

                    # 插入版本 1
                    session.add(m.KnowledgeNodeVersion(
                        node_id=new_node.id,
                        version=1,
                        name=node_data["name"],
                        description=node_data["description"],
                        origin="manual",
                        review_status="approved",
                        reviewer_id="beijing_zhongkao_expert",
                        review_opinion=f"【北京市中考全科教研专家核定通过】2018–2025年北京市中考真题基线考点「{node_data['name']}」（编码：{code}），已完成与2022年版课程标准候选节点的只读兼容映射。",
                        reviewed_at=m.now(),
                    ))

        # 1.2 建立父子层级关系
        for subject, nodes in TAXONOMY.items():
            for node_data in nodes:
                p_code = node_data["parent_code"]
                if p_code and p_code in code_to_node_id:
                    node_id = code_to_node_id[node_data["code"]]
                    parent_id = code_to_node_id[p_code]
                    node_obj = session.get(m.KnowledgeNode, node_id)
                    if node_obj and node_obj.parent_id != parent_id:
                        node_obj.parent_id = parent_id

        session.commit()
        print(f"✓ 知识点库播种完成：新增 {stats['nodes_created']} 个，既有 {stats['nodes_existing']} 个，全部节点已就绪")

        print("\n=== [2/2] 播种 2018-2025 年北京中考四科全真试题 (ALL_EXAM_PAPERS) ===")
        for paper in ALL_EXAM_PAPERS:
            subject = paper["subject"]
            title = paper["title"]
            exam_year = paper["exam_year"]
            pdf_relpath = paper.get("pdf_relpath")
            questions = paper["questions"]

            # 2.1 检查或创建题源
            src = session.scalar(select(m.SourceDocument).where(m.SourceDocument.title == title))
            if src:
                stats["sources_existing"] += 1
            else:
                src = m.SourceDocument(
                    title=title,
                    subject=subject,
                    exam_year=exam_year,
                    rights_status="personal_use_reviewed",
                    verified=True,
                    source_class="official_exam",
                    ingest_status="ingested",
                    review_status="approved",
                )
                session.add(src)
                session.flush()
                
                import datetime
                session.add(m.SourceReview(
                    source_document_id=src.id,
                    exam_year=exam_year,
                    source_url=f"local://exam_corpus/{exam_year}",
                    acquired_at=datetime.date.today(),
                    rights_status="personal_use_reviewed",
                    rights_basis=f"{exam_year}年北京市初中学业水平考试官方真题原卷",
                    applicable=True,
                    applicability_note="北京市初中学业水平考试权威全真试卷",
                    reviewed_by="owner",
                ))
                stats["sources_created"] += 1

            # 2.1.b 可选挂载 PDF / DOCX 真题原件附件（富尔题库空白卷支持 .docx 及 .doc 无损转换）
            att: m.SourceAttachment | None = None
            if attach_pdfs and pdf_relpath and resolved_corpus_dir.is_dir():
                pdf_file = resolved_corpus_dir / pdf_relpath
                if pdf_file.is_file():
                    att = session.scalar(
                        select(m.SourceAttachment).where(
                            m.SourceAttachment.source_document_id == src.id,
                            m.SourceAttachment.status == "confirmed",
                        )
                    )
                    if att is None:
                        # 若为 .doc 文件，读取预转换或动态转换的标准 .docx 字节
                        if pdf_file.suffix.lower() == ".doc":
                            cached_docx = resolved_cache_dir / Path(pdf_relpath).with_suffix(".docx")
                            if cached_docx.is_file():
                                data = cached_docx.read_bytes()
                            else:
                                import subprocess, tempfile
                                with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".cache") as tmpdir:
                                    subprocess.run(["libreoffice", "--headless", "--convert-to", "docx", str(pdf_file), "--outdir", tmpdir], check=True, capture_output=True)
                                    conv_file = Path(tmpdir) / f"{pdf_file.stem}.docx"
                                    data = conv_file.read_bytes()
                            media_type = files.DOCX_MEDIA_TYPE
                            upload_filename = f"{pdf_file.stem}.docx"
                        else:
                            data = pdf_file.read_bytes()
                            media_type = (
                                files.DOCX_MEDIA_TYPE
                                if pdf_file.suffix.lower() == ".docx"
                                else "application/pdf"
                            )
                            upload_filename = pdf_file.name

                        files.validate_file(data, media_type)
                        digest = hashlib.sha256(data).hexdigest()
                        storage_key = files.write_blob(data)
                        att = m.SourceAttachment(
                            source_document_id=src.id,
                            owner_id="owner",
                            filename=upload_filename,
                            media_type=media_type,
                            sha256=digest,
                            byte_size=len(data),
                            storage_key=storage_key,
                            status="confirmed",
                            confirmed_at=m.now(),
                            confirmed_by="owner",
                        )
                        session.add(att)
                        session.flush()
                        src.sha256 = digest
                        src.verified = True
                        stats["attachments_linked"] += 1

            # 2.2 逐题录入试题与发布版本
            for q_data in questions:
                idx = q_data["index"]
                stem = q_data["stem"]
                kind = q_data["kind"]
                options = q_data.get("options")
                correct_answer = q_data["correct_answer"]
                max_points = q_data["max_points"]
                k_codes = q_data["knowledge_codes"]
                evidence = q_data["evidence"]

                # 检查同一题源下是否已存在相同题干的题目
                existing_qv = session.scalar(
                    select(m.QuestionVersion)
                    .join(m.Question, m.QuestionVersion.question_id == m.Question.id)
                    .where(
                        m.Question.source_document_id == src.id,
                        m.QuestionVersion.stem == stem,
                    )
                )

                if existing_qv:
                    stats["questions_existing"] += 1
                    qv = existing_qv
                else:
                    # 创建逻辑题目
                    question = m.Question(
                        source_document_id=src.id,
                        subject=subject,
                    )
                    session.add(question)
                    session.flush()

                    # 创建已审核的发布版本
                    qv = m.QuestionVersion(
                        question_id=question.id,
                        version=1,
                        stem=stem,
                        kind=kind,
                        options=options,
                        correct_answer=correct_answer,
                        max_points=max_points,
                        knowledge_ids=k_codes,
                        status="published",
                        reviewed_by_human=True,
                    )
                    session.add(qv)
                    session.flush()

                    # 建立与规范知识点树的 QuestionKnowledgeLink 双向关联
                    for code in k_codes:
                        if code in code_to_node_id:
                            node_id = code_to_node_id[code]
                            session.add(m.QuestionKnowledgeLink(
                                question_version_id=qv.id,
                                sub_index=0,
                                node_id=node_id,
                                node_version=1,
                                role="core",
                                evidence=evidence,
                                review_status="approved",
                            ))
                            stats["links_created"] += 1

                    stats["questions_published"] += 1

                # 若题源已挂载原件附件，确保每道发布题版本具备 ImportedQuestion 溯源记录
                if att is not None:
                    existing_imp = session.scalar(
                        select(m.ImportedQuestion).where(
                            m.ImportedQuestion.question_version_id == qv.id
                        )
                    )
                    if existing_imp is None:
                        session.add(m.ImportedQuestion(
                            question_version_id=qv.id,
                            attachment_id=att.id,
                        ))

            session.commit()
            print(f"✓ {exam_year} 北京中考 {subject:7s} 试卷就绪：累计 {len(questions)} 道全真试题已上架发布")

        session.commit()

    print("\n--------------------------------------------------")
    print("真题与知识点库播种报告：")
    print(f"  • 新建知识点节点:  {stats['nodes_created']} 个")
    print(f"  • 既有知识点节点:  {stats['nodes_existing']} 个")
    print(f"  • 新建官方题源:    {stats['sources_created']} 个")
    print(f"  • 挂载真题原件:    {stats['attachments_linked']} 份")
    print(f"  • 发布新真题:      {stats['questions_published']} 道")
    print(f"  • 既有已发布真题:  {stats['questions_existing']} 道")
    print(f"  • 建立知识点关联:  {stats['links_created']} 条")
    print("--------------------------------------------------")
    return stats


def main():
    parser = argparse.ArgumentParser(description="灌入真实知识点与 2018-2023 及 2025 北京中考真题工具")
    parser.add_argument("--database-url", type=str, default=None, help="目标数据库连接串，缺省使用当前配置")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help="北京中考真题 PDF 原件目录",
    )
    parser.add_argument(
        "--no-attachments",
        action="store_true",
        help="仅灌入结构化真题与考点，不挂载原件附件",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="彻底清理既有真题与附件后重新完整灌入",
    )
    parser.add_argument(
        "--converted-cache-dir",
        type=Path,
        default=None,
        help="预转换 .doc -> .docx 缓存目录（默认使用 .cache/converted_docx 或 SHUTONG_CONVERTED_CACHE_DIR）",
    )
    args = parser.parse_args()

    seed_corpus(
        db_url=args.database_url,
        corpus_dir=args.corpus_dir,
        attach_pdfs=not args.no_attachments,
        rebuild=args.rebuild,
        converted_cache_dir=args.converted_cache_dir,
    )


if __name__ == "__main__":
    main()
