"""ST-003：原件仅用运行时生成的虚构测试数据。"""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shutong import models as m
from shutong.database import get_db
from shutong.main import app


@contextmanager
def database():
    yield from app.dependency_overrides[get_db]()


def synthetic_pdf(pages=1, text='SYNTHETIC TEST DATA: 1 + 1 = ?'):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               f'<< /Type /Pages /Count {pages} /Kids [{" ".join(f"{5 + i} 0 R" for i in range(pages))}] >>'.encode(),
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    stream = f'BT /F1 16 Tf 40 700 Td ({text}) Tj ET'.encode()
    objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
    objects.extend([b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>'] * pages)
    data = b'%PDF-1.4\n'
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(data)
    data += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    data += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    return data + f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


@pytest.fixture
def source(client, auth, tmp_path, monkeypatch):
    monkeypatch.setenv('SHUTONG_PRIVATE_DIR', str(tmp_path / 'private'))
    response = client.post('/api/admin/sources', headers=auth, json={
        'title': '虚构测试数据：导入题源', 'subject': 'math',
        'verified': True, 'rights_status': 'personal_use_reviewed',
    })
    assert response.status_code == 201
    return response.json()['id']


def upload(client, auth, source, data=None, media_type='application/pdf', filename='synthetic.pdf', **params):
    return client.post(f'/api/admin/sources/{source}/attachments',
                       params={'filename': filename, **params}, content=synthetic_pdf() if data is None else data,
                       headers={**auth, 'Content-Type': media_type})


def review_source(client, auth, source, **overrides):
    return client.post(f'/api/admin/sources/{source}/review', headers=auth, json={
        'exam_year': 2026, 'source_url': 'https://example.org/synthetic-only.pdf',
        'acquired_at': '2026-10-18', 'rights_status': 'personal_use_reviewed',
        'rights_basis': '虚构测试数据：人工确认可用于测试',
        'applicable': True, 'applicability_note': '虚构测试数据：适用于数学算术测试',
        'reviewed_by_human': True, **overrides,
    })


def question_body(source):
    return {'source_document_id': source, 'stem': '虚构测试数据：1+1=?',
            'options': ['A. 1', 'B. 2'], 'correct_answer': 'B',
            'knowledge_ids': ['math.arithmetic'], 'max_points': 2}


def test_pdf_import_requires_source_and_question_human_review(client, auth, source, tmp_path):
    data = synthetic_pdf()
    attached = upload(client, auth, source, data, expected_sha256=sha256(data).hexdigest())
    assert attached.status_code == 201
    meta = attached.json()
    attachment = meta['id']
    assert meta['sha256'] == sha256(data).hexdigest() and meta['byte_size'] == len(data)
    assert meta['status'] == 'uploaded'
    assert 'storage_key' not in meta and 'path' not in meta
    files = list((tmp_path / 'private').iterdir())
    assert len(files) == 1 and files[0].read_bytes() == data
    assert files[0].stat().st_mode & 0o777 == 0o600
    assert client.get(f'/api/admin/attachments/{attachment}/download').status_code == 401
    downloaded = client.get(f'/api/admin/attachments/{attachment}/download', headers=auth)
    assert downloaded.content == data
    assert downloaded.headers['content-disposition'].startswith('attachment')
    assert downloaded.headers['x-content-type-options'] == 'nosniff'
    assert client.get(f'/private-data/{files[0].name}').status_code == 404
    confirm = {'confirmed_by_human': True, 'questions': [question_body(source)]}
    assert client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth, json=confirm).status_code == 409
    parsed = client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth)
    assert parsed.status_code == 200
    assert parsed.json()['status'] == 'parsed' and 'SYNTHETIC TEST DATA' in parsed.json()['extracted_text']
    assert parsed.json()['parser_version']
    confirmed = client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth, json=confirm)
    assert confirmed.status_code == 201
    version_id = confirmed.json()['question_version_ids'][0]
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 409
    assert client.post(f'/api/admin/questions/{version_id}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 409
    assert review_source(client, auth, source).status_code == 201
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 200
    assert client.get('/api/practice/next?subject=math', headers=auth).json()['question_version_id'] == version_id
    assert client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth, json=confirm).status_code == 409
    assert client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth).status_code == 409
    ledger = client.get(f'/api/admin/sources/{source}', headers=auth)
    assert ledger.status_code == 200
    assert ledger.json()['reviews'][0]['metadata']['rights_basis'].startswith('虚构测试数据')
    assert ledger.json()['attachments'][0]['question_version_ids'] == [version_id]
    assert 'storage_key' not in str(ledger.json())


@pytest.mark.parametrize('media_type, filename', [('image/png', 'synthetic.png'), ('image/jpeg', 'synthetic.jpg')])
def test_image_ocr_is_only_an_unreviewed_text_draft(client, auth, source, media_type, filename):
    image = Image.new('RGB', (1000, 200), 'white')
    ImageDraw.Draw(image).text((20, 40), 'SYNTHETIC TEST DATA', fill='black', font=ImageFont.load_default(size=48))
    buffer = BytesIO()
    image.save(buffer, format='PNG' if media_type == 'image/png' else 'JPEG')
    attached = upload(client, auth, source, buffer.getvalue(), media_type, filename)
    assert attached.status_code == 201
    parsed = client.post(f"/api/admin/attachments/{attached.json()['id']}/parse", headers=auth)
    assert parsed.status_code == 200 and parsed.json()['status'] == 'parsed'
    assert 'SYNTHETIC' in parsed.json()['extracted_text'].upper()
    assert client.get('/api/practice/next?subject=math', headers=auth).status_code == 404


def test_empty_extraction_is_explicit_and_allows_manual_confirmation(client, auth, source):
    attached = upload(client, auth, source, synthetic_pdf(text=''))
    assert attached.status_code == 201
    attachment = attached.json()['id']
    parsed = client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth)
    assert parsed.status_code == 200 and parsed.json()['status'] == 'needs_manual_input'
    assert parsed.json()['extracted_text'] == ''
    result = client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth,
                         json={'confirmed_by_human': True, 'questions': [question_body(source)]})
    assert result.status_code == 201


@pytest.mark.parametrize('case, expected', [('unauthorized', 401), ('missing_source', 404),
    ('empty', 422), ('wrong_hash', 422), ('bad_hash', 422), ('traversal', 422),
    ('unsupported', 415), ('mismatch', 422), ('corrupt_pdf', 422), ('too_many_pages', 422), ('too_large', 413)])
def test_invalid_uploads_leave_no_files_or_rows(client, auth, source, tmp_path, case, expected):
    kwargs = {}
    if case == 'unauthorized':
        auth = {}
    elif case == 'missing_source':
        source = 'missing'
    elif case == 'empty':
        kwargs['data'] = b''
    elif case == 'wrong_hash':
        kwargs['expected_sha256'] = '0' * 64
    elif case == 'bad_hash':
        kwargs['expected_sha256'] = 'bad'
    elif case == 'traversal':
        kwargs['filename'] = '../../outside.pdf'
    elif case == 'unsupported':
        kwargs.update(media_type='image/svg+xml', data=b'<svg/>')
    elif case == 'mismatch':
        kwargs.update(media_type='image/png', data=synthetic_pdf())
    elif case == 'corrupt_pdf':
        kwargs['data'] = b'%PDF-1.4\ncorrupt'
    elif case == 'too_many_pages':
        kwargs['data'] = synthetic_pdf(pages=21)
    elif case == 'too_large':
        kwargs['data'] = b'x' * (10 * 1024 * 1024 + 1)
    assert upload(client, auth, source, **kwargs).status_code == expected
    assert not list((tmp_path / 'private').glob('*'))
    with database() as db:
        assert db.scalars(select(m.SourceAttachment)).all() == []


@pytest.mark.parametrize('operation', ['download', 'parse', 'confirm'])
def test_attachment_acl_and_tamper_check(client, auth, source, tmp_path, operation):
    response = upload(client, auth, source)
    assert response.status_code == 201
    path = f"/api/admin/attachments/{response.json()['id']}/{operation}"
    request = client.get if operation == 'download' else client.post
    assert request(path).status_code == 401
    blob = next((tmp_path / 'private').iterdir())
    blob.write_bytes(b'tampered')
    kwargs = {'json': {'confirmed_by_human': True, 'questions': [question_body(source)]}} if operation == 'confirm' else {}
    result = request(path, headers=auth, **kwargs)
    assert result.status_code == 409 and result.json()["detail"] == "ATTACHMENT_HASH_MISMATCH"


def test_upload_database_failure_cleans_blob(client, auth, source, tmp_path, monkeypatch):
    def fail_commit(self):
        raise SQLAlchemyError('test-only failure')
    monkeypatch.setattr(Session, 'commit', fail_commit)
    assert upload(client, auth, source).status_code == 503
    assert not list((tmp_path / 'private').glob('*'))


@pytest.mark.parametrize('change, expected', [({'reviewed_by_human': False}, 422),
    ({'source_url': 'http://example.org/test.pdf'}, 422), ({'exam_year': '2026'}, 422)])
def test_source_review_rejects_unconfirmed_or_invalid_metadata(client, auth, source, change, expected):
    assert review_source(client, auth, source, **change).status_code == expected


def test_new_attachment_invalidates_source_approval_and_batch_is_atomic(client, auth, source):
    assert review_source(client, auth, source).status_code == 201
    attached = upload(client, auth, source)
    assert attached.status_code == 201
    assert client.get(f'/api/admin/sources/{source}', headers=auth).json()['source']['verified'] is False
    attachment = attached.json()['id']
    assert client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth).status_code == 200
    body = {'confirmed_by_human': True, 'questions': [question_body(source), question_body('different-source')]}
    assert client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth, json=body).status_code == 409
    with database() as db:
        assert db.scalars(select(m.QuestionVersion)).all() == []
    body['questions'][1] = {**question_body(source), 'stem': '虚构测试数据：第二题'}
    response = client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth, json=body)
    assert response.status_code == 201 and len(response.json()['question_version_ids']) == 2


def confirmed_question(client, auth, source):
    attached = upload(client, auth, source).json()['id']
    assert client.post(f'/api/admin/attachments/{attached}/parse', headers=auth).status_code == 200
    response = client.post(f'/api/admin/attachments/{attached}/confirm', headers=auth,
                           json={'confirmed_by_human': True, 'questions': [question_body(source)]})
    assert response.status_code == 201
    return attached, response.json()['question_version_ids'][0]


def test_import_revision_preserves_provenance_and_checks_file_at_publication(client, auth, source, tmp_path):
    attached, original = confirmed_question(client, auth, source)
    assert review_source(client, auth, source).status_code == 201
    assert client.post(f'/api/admin/questions/{original}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{original}/publish', headers=auth).status_code == 200
    revised = client.post(f'/api/admin/questions/{original}/revisions', headers=auth, json=question_body(source))
    assert revised.status_code == 201
    version = revised.json()['id']
    with database() as db:
        assert db.get(m.ImportedQuestion, version).attachment_id == attached
    assert client.post(f'/api/admin/questions/{version}/review', headers=auth).status_code == 200
    blob = next((tmp_path / 'private').iterdir())
    original_bytes = blob.read_bytes()
    blob.write_bytes(b'tampered')
    response = client.post(f'/api/admin/questions/{version}/publish', headers=auth)
    assert response.status_code == 409 and response.json()['detail'] == 'ATTACHMENT_HASH_MISMATCH'
    blob.write_bytes(original_bytes)
    assert client.post(f'/api/admin/questions/{version}/publish', headers=auth).status_code == 200


def test_confirmation_database_failure_rolls_back_entire_batch(client, auth, source, monkeypatch):
    attachment = upload(client, auth, source).json()['id']
    assert client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth).status_code == 200
    def fail_commit(self):
        raise SQLAlchemyError('test-only failure')
    monkeypatch.setattr(Session, 'commit', fail_commit)
    response = client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth,
                           json={'confirmed_by_human': True, 'questions': [question_body(source)] * 2})
    assert response.status_code == 503
    with database() as db:
        assert db.get(m.SourceAttachment, attachment).status == 'parsed'
        assert db.scalars(select(m.Question)).all() == []
        assert db.scalars(select(m.QuestionVersion)).all() == []
        assert db.scalars(select(m.ImportedQuestion)).all() == []


@pytest.mark.parametrize('change', [{'applicable': False}, {'rights_status': 'unknown'}])
def test_source_review_does_not_bypass_applicability_or_rights_gate(client, auth, source, change):
    _, version = confirmed_question(client, auth, source)
    assert review_source(client, auth, source, **change).status_code == 201
    assert client.post(f'/api/admin/questions/{version}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{version}/publish', headers=auth).status_code == 409


def test_legacy_create_route_cannot_bypass_attachment_confirmation(client, auth, source):
    assert upload(client, auth, source).status_code == 201
    assert review_source(client, auth, source).status_code == 201
    response = client.post('/api/admin/questions', headers=auth, json=question_body(source))
    assert response.status_code == 201
    version = response.json()['id']
    assert client.post(f'/api/admin/questions/{version}/review', headers=auth).status_code == 200
    result = client.post(f'/api/admin/questions/{version}/publish', headers=auth)
    assert result.status_code == 409 and result.json()['detail'] == 'IMPORTED_QUESTION_CONFIRMATION_REQUIRED'


def test_attachment_owner_and_all_metadata_routes_require_authentication(client, auth, source):
    attachment = upload(client, auth, source).json()['id']
    for path in ['/api/admin/sources', f'/api/admin/sources/{source}', f'/api/admin/attachments/{attachment}']:
        assert client.get(path).status_code == 401
    assert review_source(client, {}, source).status_code == 401
    with database() as db:
        db.get(m.SourceAttachment, attachment).owner_id = 'other-owner'
        db.commit()
    assert client.get(f'/api/admin/attachments/{attachment}', headers=auth).status_code == 404
    assert client.get(f'/api/admin/attachments/{attachment}/download', headers=auth).status_code == 404
    assert client.get(f'/api/admin/sources/{source}', headers=auth).json()['attachments'] == []


@pytest.mark.parametrize('failure, expected', [('missing', 503), ('timeout', 422)])
def test_parser_failure_leaves_import_unparsed(client, auth, source, monkeypatch, failure, expected):
    import subprocess
    from shutong import private_files
    attachment = upload(client, auth, source).json()['id']
    def fail_run(*args, **kwargs):
        if failure == 'missing':
            raise FileNotFoundError('test-only missing binary')
        raise subprocess.TimeoutExpired('test-only parser', 20)
    monkeypatch.setattr(private_files.subprocess, 'run', fail_run)
    assert client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth).status_code == expected
    with database() as db:
        row = db.get(m.SourceAttachment, attachment)
        assert row.status == 'uploaded' and row.extracted_text is None


@pytest.mark.parametrize('change', [{'confirmed_by_human': False}, {'confirmed_by_human': 'true'}, {'questions': []}])
def test_confirmation_requires_explicit_human_and_nonempty_batch(client, auth, source, change):
    attachment = upload(client, auth, source).json()['id']
    assert client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth).status_code == 200
    result = client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth,
                         json={'confirmed_by_human': True, 'questions': [question_body(source)], **change})
    assert result.status_code == 422
    with database() as db:
        assert db.get(m.SourceAttachment, attachment).status == 'parsed'
        assert db.scalars(select(m.Question)).all() == []


def test_storage_collision_does_not_delete_existing_file(client, auth, source, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from shutong import private_files
    root = tmp_path / 'private'
    root.mkdir()
    existing = root / ('a' * 32)
    existing.write_bytes(b'existing synthetic test data')
    monkeypatch.setattr(private_files, 'uuid4', lambda: SimpleNamespace(hex='a' * 32))
    assert upload(client, auth, source).status_code == 503
    assert existing.read_bytes() == b'existing synthetic test data'
    with database() as db:
        assert db.scalars(select(m.SourceAttachment)).all() == []
