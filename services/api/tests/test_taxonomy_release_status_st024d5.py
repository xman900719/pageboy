"""ST-024-D5: synthetic isolated release-state regression tests."""
from datetime import datetime, timedelta, timezone
import copy

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from shutong import fourcorpus, models as m
from shutong.database import get_db
from shutong.learning_api import _load_effective_knowledge_nodes
from shutong.taxonomy_audit import (audit_and_publish_subject, publish_subject_taxonomy_release,
                                   seed_and_approve_subject)


def test_cli_publishes_and_is_idempotent(client):
    with next(client.app.dependency_overrides[get_db]()) as db:
        for subject in ("chinese", "english", "math", "physics"):
            result = audit_and_publish_subject(db, subject, reviewer_id="synthetic-test-reviewer")
            row = db.get(m.KnowledgeTaxonomyRelease, result["release_id"])
            assert result["release_status"] == row.status == "published"
            assert row.snapshot["curriculum_sources"]
            before = copy.deepcopy(row.snapshot)
            again = publish_subject_taxonomy_release(db, subject)
            assert again["status"] == "already_published"
            db.refresh(row)
            assert row.snapshot == before


@pytest.mark.parametrize("status", ["draft", "archived"])
def test_existing_nonpublished_is_not_promoted(client, status):
    with next(client.app.dependency_overrides[get_db]()) as db:
        row = m.KnowledgeTaxonomyRelease(subject="math", release_version="math-v2022.1.0",
                                        status=status, snapshot={"nodes": []})
        db.add(row); db.commit()
        for force in (False, True):
            with pytest.raises(ValueError, match="RELEASE_STATE_NOT_PUBLISHED"):
                audit_and_publish_subject(db, "math", force_update_existing=force)
            with pytest.raises(ValueError, match="RELEASE_STATE_NOT_PUBLISHED"):
                publish_subject_taxonomy_release(db, "math", force_update_existing=force)
        db.refresh(row)
        assert row.status == status and row.snapshot == {"nodes": []}
        assert db.scalars(select(m.KnowledgeNode)).all() == []


def test_reader_skips_newer_draft_and_archived(client):
    with next(client.app.dependency_overrides[get_db]()) as db:
        result = audit_and_publish_subject(db, "math", reviewer_id="synthetic-test-reviewer")
        row = db.get(m.KnowledgeTaxonomyRelease, result["release_id"])
        expected, version = _load_effective_knowledge_nodes(db, "math")
        assert version == row.release_version and expected
        for i, status in enumerate(("draft", "archived"), 1):
            db.add(m.KnowledgeTaxonomyRelease(subject="math", release_version=f"math-{status}",
                   status=status, published_at=datetime.now(timezone.utc)+timedelta(days=i),
                   snapshot={"nodes": [{"code": "math.fake.synthetic", "name": "虚构测试数据"}]}))
        db.commit()
        assert _load_effective_knowledge_nodes(db, "math") == (expected, version)
        row.status = "archived"; db.commit()
        nodes, version = _load_effective_knowledge_nodes(db, "math")
        assert version is None and all(n["code"] != "math.fake.synthetic" for n in nodes)


def test_cli_uses_formal_pdf_gate(client, tmp_path, monkeypatch):
    with next(client.app.dependency_overrides[get_db]()) as db:
        seed_and_approve_subject(db, "math", reviewer_id="synthetic-test-reviewer")
        missing = tmp_path / "missing-pdfs"
        monkeypatch.setattr(fourcorpus, "curriculum_standards_dir", lambda: missing)
        with pytest.raises(HTTPException) as e:
            publish_subject_taxonomy_release(db, "math")
        assert e.value.status_code == 400 and ("PDF" in e.value.detail or "课标原件" in e.value.detail)
        assert db.scalars(select(m.KnowledgeTaxonomyRelease)).all() == []
