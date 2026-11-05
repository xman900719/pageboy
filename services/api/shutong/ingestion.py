"""私有内容导入编排：原件、来源审核、文本草稿与人工确认。"""
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import models as m
from .auth import require_owner
from .content import create_question_draft
from .database import get_db
from . import private_files as files
from .schemas import AttachmentOut, ImportConfirmationIn, QuestionVersionOut, SourceDetailOut, SourceIn, SourceReviewIn, SourceReviewRecordOut

router = APIRouter(prefix="/api/admin", tags=["private content ingestion"])


def source_or_404(db, source_id):
    source = db.get(m.SourceDocument, source_id)
    if source is None:
        raise HTTPException(404, detail="source not found")
    return source


def attachment_or_404(db, attachment_id, owner):
    attachment = db.get(m.SourceAttachment, attachment_id)
    if attachment is None or attachment.owner_id != owner:
        raise HTTPException(404, detail="attachment not found")
    return attachment


def attachment_data(db, attachment):
    data = {name: getattr(attachment, name) for name in AttachmentOut.model_fields if name != "question_version_ids"}
    data["question_version_ids"] = db.scalars(select(m.ImportedQuestion.question_version_id).where(
        m.ImportedQuestion.attachment_id == attachment.id).order_by(m.ImportedQuestion.question_version_id)).all()
    return data


def review_data(review):
    metadata = {name: getattr(review, name) for name in SourceReviewIn.model_fields if name != "reviewed_by_human"}
    return {"id": review.id, "metadata": {**metadata, "reviewed_by_human": True},
            "reviewed_by": review.reviewed_by, "created_at": review.created_at}


@router.get("/sources/{source_id}", response_model=SourceDetailOut)
def source_details(source_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    source = source_or_404(db, source_id)
    reviews = db.scalars(select(m.SourceReview).where(m.SourceReview.source_document_id == source_id).order_by(m.SourceReview.created_at, m.SourceReview.id)).all()
    attachments = db.scalars(select(m.SourceAttachment).where(m.SourceAttachment.source_document_id == source_id, m.SourceAttachment.owner_id == owner).order_by(m.SourceAttachment.created_at, m.SourceAttachment.id)).all()
    source_info = {name: getattr(source, name) for name in SourceIn.model_fields}
    # 老记录的来源级哈希可能只是人工输入，不能作为原件存在的证据。
    source_info["sha256"] = attachments[0].sha256 if attachments else None
    return {"id": source.id, "source": source_info,
            "reviews": [review_data(review) for review in reviews], "attachments": [attachment_data(db, item) for item in attachments]}


@router.get("/sources", response_model=list[SourceDetailOut])
def source_ledger(owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    sources = db.scalars(select(m.SourceDocument).order_by(m.SourceDocument.created_at, m.SourceDocument.id)).all()
    return [source_details(source.id, owner, db) for source in sources]


@router.get("/sources/{source_id}/questions", response_model=list[QuestionVersionOut])
def list_source_question_versions(source_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """审核台只读列表：按题源回读全部版本（含草稿）的内容与状态，供人工审核 UI 回显。
    不新增字节读取路由；存储键不进响应（QuestionVersionOut 无此字段）。"""
    source_or_404(db, source_id)
    rows = db.execute(select(m.QuestionVersion)
                       .join(m.Question, m.Question.id == m.QuestionVersion.question_id)
                       .where(m.Question.source_document_id == source_id)
                       .order_by(m.QuestionVersion.question_id, m.QuestionVersion.version)).scalars().all()
    return rows


@router.post("/sources/{source_id}/review", status_code=201, response_model=SourceReviewRecordOut)
def review_source(source_id: str, payload: SourceReviewIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    source = source_or_404(db, source_id)
    source.exam_year = payload.exam_year
    source.source_url = str(payload.source_url)
    source.rights_status = payload.rights_status
    source.verified = payload.applicable
    review = m.SourceReview(source_document_id=source.id, reviewed_by=owner, acquired_at=payload.acquired_at,
                            **payload.model_dump(mode="json", exclude={"reviewed_by_human", "acquired_at"}))
    db.add(review)
    db.commit()
    db.refresh(review)
    return review_data(review)


def save_attachment(db, source_id, owner, filename, media_type, data, expected_sha256):
    source = source_or_404(db, source_id)
    files.validate_file(data, media_type)
    digest = sha256(data).hexdigest()
    if expected_sha256 is not None and expected_sha256 != digest:
        raise HTTPException(422, detail="UPLOAD_HASH_MISMATCH")
    # 来源级 SHA256 锚定首次上传的文件。后续音频、图片等补充附件不能覆写它。
    first_attachment = db.scalars(select(m.SourceAttachment).where(
        m.SourceAttachment.source_document_id == source.id).order_by(
        m.SourceAttachment.created_at, m.SourceAttachment.id).limit(1)).first()
    key = None
    try:
        key = files.write_blob(data)
        attachment = m.SourceAttachment(source_document_id=source.id, owner_id=owner, filename=filename,
                                        media_type=media_type, sha256=digest, byte_size=len(data), storage_key=key)
        # 旧记录如有未经原件核对的手填哈希，以已有附件的服务端哈希校正。
        source.sha256 = first_attachment.sha256 if first_attachment is not None else digest
        source.verified = False
        db.add(attachment)
        db.commit()
    except (OSError, SQLAlchemyError):
        db.rollback()
        if key is not None:
            files.blob_path(key).unlink(missing_ok=True)
        raise HTTPException(503, detail="ATTACHMENT_STORAGE_UNAVAILABLE")
    db.refresh(attachment)
    return attachment_data(db, attachment)


@router.post("/sources/{source_id}/attachments", status_code=201, response_model=AttachmentOut,
             openapi_extra={"requestBody": {"required": True, "content": {
                 media: {"schema": {"type": "string", "format": "binary"}} for media in files.MEDIA_TYPES}}})
async def upload_attachment(source_id: str, request: Request,
                            filename: str = Query(min_length=1, max_length=255, pattern=r"^[^/\\\x00-\x1f\x7f]+$"),
                            expected_sha256: str | None = Query(default=None, pattern="^[0-9a-f]{64}$"),
                            owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    """原始二进制请求体；上限 10 MiB，不使用公开目录或外部下载 URL。"""
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in files.MEDIA_TYPES:
        raise HTTPException(415, detail="UNSUPPORTED_FILE_TYPE")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > files.MAX_BYTES:
            raise HTTPException(413, detail="INVALID_FILE_SIZE")
        data.extend(chunk)
    return await run_in_threadpool(save_attachment, db, source_id, owner, filename, media_type, bytes(data), expected_sha256)


@router.get("/attachments/{attachment_id}", response_model=AttachmentOut)
def get_attachment(attachment_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    return attachment_data(db, attachment_or_404(db, attachment_id, owner))


@router.get("/attachments/{attachment_id}/download", response_class=Response)
def download_attachment(attachment_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    attachment = attachment_or_404(db, attachment_id, owner)
    return Response(files.load_blob(attachment), media_type=attachment.media_type,
                    headers={"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.post("/attachments/{attachment_id}/parse", response_model=AttachmentOut)
def parse_attachment(attachment_id: str, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    attachment = attachment_or_404(db, attachment_id, owner)
    data = files.load_blob(attachment)
    if attachment.status == "confirmed":
        raise HTTPException(409, detail="IMPORT_ALREADY_CONFIRMED")
    if attachment.media_type.startswith("audio/"):
        # 音频不跑 pdftotext/tesseract（无转写）：直接转人工录入，走既有 confirm-import（ST-007 §2）。
        text, version = None, None
    else:
        text, version = files.parse_text(data, attachment.media_type)
    result = db.execute(update(m.SourceAttachment).where(m.SourceAttachment.id == attachment.id,
                        m.SourceAttachment.status != "confirmed").values(extracted_text=text, parser_version=version,
                        parsed_at=m.now(), status="parsed" if text else "needs_manual_input"))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, detail="IMPORT_ALREADY_CONFIRMED")
    db.commit()
    db.refresh(attachment)
    return attachment_data(db, attachment)


@router.post("/attachments/{attachment_id}/confirm", status_code=201, response_model=AttachmentOut)
def confirm_import(attachment_id: str, payload: ImportConfirmationIn, owner: str = Depends(require_owner), db: Session = Depends(get_db)):
    attachment = attachment_or_404(db, attachment_id, owner)
    files.load_blob(attachment)
    if any(question.source_document_id != attachment.source_document_id for question in payload.questions):
        raise HTTPException(409, detail="IMPORT_SOURCE_MISMATCH")
    result = db.execute(update(m.SourceAttachment).where(m.SourceAttachment.id == attachment.id,
                        m.SourceAttachment.status.in_(["parsed", "needs_manual_input"])).values(
                        status="confirmed", confirmed_at=m.now(), confirmed_by=owner))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, detail="IMPORT_NOT_READY_OR_ALREADY_CONFIRMED")
    source = source_or_404(db, attachment.source_document_id)
    try:
        for question in payload.questions:
            if question.media_attachment_id is not None:
                media = db.get(m.SourceAttachment, question.media_attachment_id)
                if media is None or media.source_document_id != attachment.source_document_id or media.owner_id != owner:
                    raise HTTPException(422, detail="MEDIA_ATTACHMENT_INVALID")
            version = create_question_draft(db, source, question)
            db.add(m.ImportedQuestion(question_version_id=version.id, attachment_id=attachment.id))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, detail="IMPORT_TRANSACTION_FAILED")
    db.refresh(attachment)
    return attachment_data(db, attachment)


def require_import_integrity(db, version):
    """带原件的来源须经过导入确认；修订沿用原件追溯关系。"""
    question = db.get(m.Question, version.question_id)
    has_files = db.scalar(select(m.SourceAttachment.id).where(m.SourceAttachment.source_document_id == question.source_document_id).limit(1))
    if not has_files:
        return
    link = db.get(m.ImportedQuestion, version.id)
    if link is None:
        raise HTTPException(409, detail="IMPORTED_QUESTION_CONFIRMATION_REQUIRED")
    attachment = db.get(m.SourceAttachment, link.attachment_id)
    if attachment.status != "confirmed":
        raise HTTPException(409, detail="IMPORTED_QUESTION_CONFIRMATION_REQUIRED")
    files.load_blob(attachment)
