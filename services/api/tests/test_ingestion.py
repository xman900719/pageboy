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


def scanned_pdf(pages=1, text='SYNTHETIC TEST DATA'):
    # 图像型 PDF（无文本层，模拟扫描件）：PIL 将位图保存为 PDF，运行时生成、绝不使用真实原卷。
    images = []
    for _ in range(pages):
        image = Image.new('RGB', (1000, 200), 'white')
        ImageDraw.Draw(image).text((20, 60), text, fill='black', font=ImageFont.load_default(size=48))
        images.append(image)
    buffer = BytesIO()
    images[0].save(buffer, format='PDF', save_all=True, append_images=images[1:])
    return buffer.getvalue()


def synthetic_docx(text='SYNTHETIC TEST DATA: 2024 DOCX QUESTION'):
    """运行时生成合法最小 .docx（ZIP 内含 word/document.xml），绝不使用真实原卷。"""
    import zipfile
    buf = BytesIO()
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>'
        '</w:document>'
    )
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('word/document.xml', doc_xml.encode('utf-8'))
    return buf.getvalue()


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




def test_source_hash_requires_real_upload(client, auth):
    # 无原件的来源登记不能将任意 64 位字符串标记为已核验 SHA256。
    response = client.post('/api/admin/sources', headers=auth, json={
        'title': '虚构测试数据：无原件伪哈希', 'subject': 'math', 'sha256': 'a' * 64,
    })
    assert response.status_code == 422
    assert response.json()['detail'] == 'SOURCE_HASH_REQUIRES_ATTACHMENT_UPLOAD'
    with database() as db:
        assert db.scalars(select(m.SourceDocument).where(
            m.SourceDocument.title == '虚构测试数据：无原件伪哈希')).all() == []


def test_source_hash_derived_from_first_uploaded_attachment(client, auth, source):
    details = client.get(f'/api/admin/sources/{source}', headers=auth).json()
    assert details['source']['sha256'] is None

    first = synthetic_pdf(text='first synthetic data')
    expected = sha256(first).hexdigest()
    bad = upload(client, auth, source, first, expected_sha256='0' * 64)
    assert bad.status_code == 422
    assert client.get(f'/api/admin/sources/{source}', headers=auth).json()['source']['sha256'] is None

    attached = upload(client, auth, source, first, expected_sha256=expected)
    assert attached.status_code == 201
    assert attached.json()['sha256'] == expected
    details = client.get(f'/api/admin/sources/{source}', headers=auth).json()
    assert details['source']['sha256'] == expected
    with database() as db:
        assert db.get(m.SourceDocument, source).sha256 == expected

    second = synthetic_pdf(text='second synthetic data')
    assert sha256(second).hexdigest() != expected
    extra = upload(client, auth, source, second)
    assert extra.status_code == 201
    assert extra.json()['sha256'] == sha256(second).hexdigest()
    assert client.get(f'/api/admin/sources/{source}', headers=auth).json()['source']['sha256'] == expected
    with database() as db:
        assert db.get(m.SourceDocument, source).sha256 == expected


def test_legacy_unbacked_source_hash_is_not_presented_as_verified(client, auth, source):
    with database() as db:
        db.get(m.SourceDocument, source).sha256 = 'a' * 64
        db.commit()
    # 旧库的人工输入哈希不在无附件时作为可信原件哈希回显。
    details = client.get(f'/api/admin/sources/{source}', headers=auth).json()
    assert details['source']['sha256'] is None
    assert upload(client, auth, source).status_code == 201
    details = client.get(f'/api/admin/sources/{source}', headers=auth).json()
    assert details['source']['sha256'] == details['attachments'][0]['sha256']
    assert details['source']['sha256'] != 'a' * 64


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


def test_pdf_needs_ocr_only_when_extraction_has_no_visible_characters():
    from shutong.private_files import pdf_needs_ocr
    assert pdf_needs_ocr('') is True
    assert pdf_needs_ocr('  \n\t \x0c ') is True
    assert pdf_needs_ocr('扫描全能王 创建 \x0c 扫描全能王 创建') is True
    assert pdf_needs_ocr('帮 考 京 ： 号 众 公 \x0c 帮 考 京 ： 号 众 公') is True
    assert pdf_needs_ocr('{#{QQABZYCAggAgAgAAAQACAwHgCgCQkhACACgOBBAYoEAAiBFABCA=}#}\x0c{#{QQABZYCAggAgAgAAAQACAwHgCgCQkhACACgOBBAYoEAAiBFABCA=}#}') is True
    assert pdf_needs_ocr('··· ··\x0c·· ···') is True
    assert pdf_needs_ocr('２０２３年北京市初中学业水平考试' + '\x0c' * 5) is True
    assert pdf_needs_ocr('SYNTHETIC TEST DATA') is False
    assert pdf_needs_ocr('  \x0c\n文本层\n ') is False


def test_scanned_pdf_without_text_layer_falls_back_to_ocr(client, auth, source, tmp_path):
    import subprocess
    data = scanned_pdf()
    # 前置断言：该 PDF 确实没有文本层，否则本用例不能证明 OCR 兜底被触发。
    probe, extracted = tmp_path / 'probe.pdf', tmp_path / 'probe.txt'
    probe.write_bytes(data)
    subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(probe), str(extracted)], check=True)
    assert extracted.read_text().strip() == ''
    attached = upload(client, auth, source, data)
    assert attached.status_code == 201
    parsed = client.post(f"/api/admin/attachments/{attached.json()['id']}/parse", headers=auth)
    assert parsed.status_code == 200 and parsed.json()['status'] == 'parsed'
    body = parsed.json()
    assert 'SYNTHETIC' in body['extracted_text'].upper()
    assert '第 1 页（OCR 草稿）' in body['extracted_text']
    assert 'tesseract' in body['parser_version'] and 'pdftotext' in body['parser_version']


def test_scanned_pdf_ocr_marks_pages_in_order(client, auth, source):
    data = scanned_pdf(pages=2, text='SYNTHETIC MULTI PAGE')
    attached = upload(client, auth, source, data)
    assert attached.status_code == 201
    parsed = client.post(f"/api/admin/attachments/{attached.json()['id']}/parse", headers=auth)
    assert parsed.status_code == 200
    text = parsed.json()['extracted_text']
    assert '第 1 页（OCR 草稿）' in text and '第 2 页（OCR 草稿）' in text
    assert text.index('第 1 页') < text.index('第 2 页')


def test_text_layer_pdf_does_not_enter_ocr_fallback(client, auth, source):
    # 反例：有文本层的 PDF 必须只走 pdftotext，不得降级 OCR、parser_version 不得出现 tesseract。
    attached = upload(client, auth, source)
    assert attached.status_code == 201
    parsed = client.post(f"/api/admin/attachments/{attached.json()['id']}/parse", headers=auth)
    assert parsed.status_code == 200
    assert 'SYNTHETIC TEST DATA' in parsed.json()['extracted_text']
    assert parsed.json()['parser_version'].startswith('pdftotext')
    assert 'tesseract' not in parsed.json()['parser_version']


def test_scanned_pdf_page_cap_applies_at_upload(client, auth, source, tmp_path):
    assert upload(client, auth, source, scanned_pdf(pages=41)).status_code == 422
    assert not list((tmp_path / 'private').glob('*'))


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
        kwargs['data'] = synthetic_pdf(pages=41)
    elif case == 'too_large':
        kwargs['data'] = b'x' * (35 * 1024 * 1024 + 1)
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


def test_source_question_versions_list_lifecycle(client, auth, source):
    # 审核台只读列表：未授权 401、未知来源 404、新来源为空。
    assert client.get(f'/api/admin/sources/{source}/questions').status_code == 401
    assert client.get('/api/admin/sources/none/questions', headers=auth).status_code == 404
    listing = client.get(f'/api/admin/sources/{source}/questions', headers=auth)
    assert listing.status_code == 200 and listing.json() == []

    # 直接创建的草稿：审核所需字段逐项可回读，reviewed_by_human 如实为 False。
    created = client.post('/api/admin/questions', headers=auth,
                          json={**question_body(source), 'group_context': '虚构测试数据：共享阅读材料'})
    assert created.status_code == 201
    direct = created.json()['id']
    rows = client.get(f'/api/admin/sources/{source}/questions', headers=auth).json()
    assert len(rows) == 1
    item = rows[0]
    assert item['id'] == direct and item['question_id'] and item['version'] == 1
    assert item['status'] == 'draft' and item['reviewed_by_human'] is False
    assert item['stem'] == '虚构测试数据：1+1=?'
    assert item['kind'] == 'single_choice' and item['options'] == ['A. 1', 'B. 2']
    assert item['correct_answer'] == 'B' and item['knowledge_ids'] == ['math.arithmetic']
    assert item['max_points'] == 2 and item['group_context'] == '虚构测试数据：共享阅读材料'
    assert item['media_attachment_id'] is None

    # 附件导入路径产生的草稿同样可见（与直接创建的并列，序按 question_id+version）。
    attachment = upload(client, auth, source).json()['id']
    assert client.post(f'/api/admin/attachments/{attachment}/parse', headers=auth).status_code == 200
    confirmed = client.post(f'/api/admin/attachments/{attachment}/confirm', headers=auth,
                            json={'confirmed_by_human': True, 'questions': [question_body(source)]})
    assert confirmed.status_code == 201
    imported = confirmed.json()['question_version_ids'][0]
    rows = client.get(f'/api/admin/sources/{source}/questions', headers=auth).json()
    assert {row['id'] for row in rows} == {direct, imported}

    # 审核 → 发布后列表如实反映状态；未审核草稿保持 draft。
    assert client.post(f'/api/admin/questions/{imported}/review', headers=auth).status_code == 200
    assert review_source(client, auth, source).status_code == 201
    assert client.post(f'/api/admin/questions/{imported}/publish', headers=auth).status_code == 200
    by_id = {row['id']: row for row in client.get(f'/api/admin/sources/{source}/questions', headers=auth).json()}
    assert by_id[direct]['status'] == 'draft' and by_id[direct]['reviewed_by_human'] is False
    assert by_id[imported]['status'] == 'published' and by_id[imported]['reviewed_by_human'] is True


def test_source_question_versions_list_isolation_and_revisions(client, auth, source):
    # 隔离：另一题源的版本不泄入本源列表。
    other = client.post('/api/admin/sources', headers=auth,
                         json={'title': '虚构测试数据：隔离题源', 'subject': 'math'}).json()['id']
    assert client.post('/api/admin/questions', json=question_body(other), headers=auth).status_code == 201
    assert client.get(f'/api/admin/sources/{source}/questions', headers=auth).json() == []
    other_rows = client.get(f'/api/admin/sources/{other}/questions', headers=auth).json()
    assert len(other_rows) == 1

    # 已发布题的修订生成 v2 草稿：与 v1 published 并列可见，状态分层如实。
    version = other_rows[0]['id']
    assert client.post(f'/api/admin/questions/{version}/review', headers=auth).status_code == 200
    assert review_source(client, auth, other).status_code == 201
    assert client.post(f'/api/admin/questions/{version}/publish', headers=auth).status_code == 200
    revised = client.post(f'/api/admin/questions/{version}/revisions', headers=auth,
                          json={**question_body(other), 'stem': '虚构测试数据：修订题干'})
    assert revised.status_code == 201
    rows = client.get(f'/api/admin/sources/{other}/questions', headers=auth).json()
    same_question = sorted((row['version'], row['status']) for row in rows
                           if row['question_id'] == revised.json()['question_id'])
    assert same_question == [(1, 'published'), (2, 'draft')]


def test_source_ledger_tolerates_local_scheme_source_url(client, auth, source):
    """本地语料种子的 local:// 来源地址不得使读取接口 500；写入侧仍强制 HTTPS。"""
    with database() as db:
        review = m.SourceReview(source_document_id=source, exam_year=2025, source_url='local://exam_corpus/2025',
                                acquired_at=__import__('datetime').date(2025, 1, 1), rights_status='unknown',
                                rights_basis='虚构测试数据', applicable=True, applicability_note='虚构测试数据',
                                reviewed_by='owner')
        db.add(review)
        db.commit()
    res = client.get('/api/admin/sources', headers=auth)
    assert res.status_code == 200
    urls = [r['metadata']['source_url'] for s in res.json() for r in s['reviews']]
    assert 'local://exam_corpus/2025' in urls
    assert review_source(client, auth, source, source_url='http://insecure.example/x').status_code == 422


def test_docx_upload_parse_and_invalid_rejection(client, auth, source):
    """验证 Word .docx 原件上传、正文解析（python-docx-xml）与损坏/伪造 .docx 拒绝。"""
    from shutong.private_files import DOCX_MEDIA_TYPE
    import zipfile

    # 正例：合法 .docx 上传并解析成功
    data = synthetic_docx('虚构测试数据：2024年数学第1题 x^2 - 4x + c = 0')
    res = upload(client, auth, source, data=data, media_type=DOCX_MEDIA_TYPE, filename='synthetic-2024.docx')
    assert res.status_code == 201
    att_id = res.json()['id']
    parsed = client.post(f'/api/admin/attachments/{att_id}/parse', headers=auth)
    assert parsed.status_code == 200
    assert parsed.json()['status'] == 'parsed'
    assert parsed.json()['parser_version'] == 'python-docx-xml'
    assert '虚构测试数据：2024年数学第1题' in parsed.json()['extracted_text']

    # 反例 1：非 ZIP 伪装成 .docx -> 422 FILE_TYPE_MISMATCH
    bad_magic = upload(client, auth, source, data=b'not a zip file', media_type=DOCX_MEDIA_TYPE, filename='bad.docx')
    assert bad_magic.status_code == 422
    assert bad_magic.json()['detail'] == 'FILE_TYPE_MISMATCH'

    # 反例 2：合法 ZIP 但缺少 word/document.xml -> 422 INVALID_DOCX
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('other.txt', b'hello')
    no_doc = upload(client, auth, source, data=buf.getvalue(), media_type=DOCX_MEDIA_TYPE, filename='nodoc.docx')
    assert no_doc.status_code == 422
    assert no_doc.json()['detail'] == 'INVALID_DOCX'
