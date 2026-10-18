"""题目草稿创建；事务由调用方统一提交。"""
from . import models as m


def create_question_draft(db, source, payload):
    question = m.Question(source_document_id=source.id, subject=source.subject)
    db.add(question)
    db.flush()
    version = m.QuestionVersion(question_id=question.id, version=1,
                                **payload.model_dump(exclude={"source_document_id"}))
    db.add(version)
    db.flush()
    return version
