"""ST-007：使用虚构测试数据验证听力题音频附件引用与导入发布链（AC-SEC 复用内容附件边界）。"""
import pytest


@pytest.fixture
def private_dir(tmp_path, monkeypatch):
    root = tmp_path / 'private'
    monkeypatch.setenv('SHUTONG_PRIVATE_DIR', str(root))
    return root


def synthetic_mp3():
    # ID3v2 魔数 + 零填充：运行时合成的虚构测试字节，绝无真实音频内容。
    return b'ID3' + b'\x03\x00\x00\x00' + b'\x00' * 500


def make_source(client, auth, subject, title):
    response = client.post('/api/admin/sources', headers=auth, json={
        'title': title, 'subject': subject, 'rights_status': 'personal_use_reviewed', 'verified': True,
    })
    assert response.status_code == 201
    return response.json()['id']


def upload_audio(client, auth, source, data=None, media_type='audio/mpeg', filename='虚构测试数据-听力.mp3'):
    # 镜像 test_ingestion.py 的上传约定：filename 走查询参数、原始字节做请求体。
    return client.post(f'/api/admin/sources/{source}/attachments', params={'filename': filename},
                       content=synthetic_mp3() if data is None else data,
                       headers={**auth, 'Content-Type': media_type})


def review_source(client, auth, source):
    return client.post(f'/api/admin/sources/{source}/review', headers=auth, json={
        'exam_year': 2026, 'source_url': 'https://example.org/synthetic-only.mp3',
        'acquired_at': '2026-10-18', 'rights_status': 'personal_use_reviewed',
        'rights_basis': '虚构测试数据：人工确认可用于测试',
        'applicable': True, 'applicability_note': '虚构测试数据：适用于英语听力测试',
        'reviewed_by_human': True,
    })


def test_audio_upload_parse_confirm_import_publish_serve(client, auth, student_auth, private_dir):
    source = make_source(client, auth, 'english', '虚构测试数据：英语听力题源')
    audio = synthetic_mp3()
    attached = upload_audio(client, auth, source, data=audio)
    assert attached.status_code == 201
    meta = attached.json()
    attachment_id = meta['id']
    assert meta['media_type'] == 'audio/mpeg'
    assert meta['status'] == 'uploaded'

    parsed = client.post(f'/api/admin/attachments/{attachment_id}/parse', headers=auth)
    assert parsed.status_code == 200
    assert parsed.json()['status'] == 'needs_manual_input'
    assert parsed.json()['extracted_text'] is None
    assert parsed.json()['parser_version'] is None

    listening_question = {
        'source_document_id': source, 'stem': '虚构测试数据：听录音选出提到的单词',
        'kind': 'single_choice', 'options': ['A. apple', 'B. banana'], 'correct_answer': 'A',
        'knowledge_ids': ['english.listening'], 'max_points': 1, 'media_attachment_id': attachment_id,
    }
    confirmed = client.post(f'/api/admin/attachments/{attachment_id}/confirm', headers=auth,
                            json={'confirmed_by_human': True, 'questions': [listening_question]})
    assert confirmed.status_code == 201
    assert confirmed.json()['status'] == 'confirmed'
    version_ids = confirmed.json()['question_version_ids']
    assert len(version_ids) == 1
    version_id = version_ids[0]

    # 上传会使来源失效，须重走来源审核；导入完整链存在，发布门禁放行。
    assert review_source(client, auth, source).status_code == 201
    assert client.post(f'/api/admin/questions/{version_id}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 200

    item = client.get('/api/practice/next?subject=english', headers=student_auth).json()
    assert item['question_version_id'] == version_id
    assert item['media_attachment_id'] == attachment_id

    downloaded = client.get(f'/api/admin/attachments/{attachment_id}/download', headers=auth)
    assert downloaded.status_code == 200
    assert downloaded.content == audio
    assert downloaded.headers['content-type'] == 'audio/mpeg'


def test_audio_validation(client, auth, private_dir):
    source = make_source(client, auth, 'english', '虚构测试数据：音频校验题源')
    mismatch = upload_audio(client, auth, source, data=b'not-really-audio' + b'\x00' * 100,
                            filename='虚构测试数据-非音频.mp3')
    assert mismatch.status_code == 422
    assert mismatch.json()['detail'] == 'FILE_TYPE_MISMATCH'
    unsupported = upload_audio(client, auth, source, media_type='audio/x-wav',
                               filename='虚构测试数据-不支持的类型.wav')
    assert unsupported.status_code == 415
    assert unsupported.json()['detail'] == 'UNSUPPORTED_FILE_TYPE'
    mp4 = b'\x00\x00\x00\x20ftypM4A ' + b'\x00' * 100
    accepted = upload_audio(client, auth, source, data=mp4, media_type='audio/mp4',
                            filename='虚构测试数据-听力.m4a')
    assert accepted.status_code == 201
    assert accepted.json()['media_type'] == 'audio/mp4'


def test_media_reference_validation(client, auth, private_dir):
    source_x = make_source(client, auth, 'math', '虚构测试数据：引用校验题源X')
    source_y = make_source(client, auth, 'math', '虚构测试数据：引用校验题源Y')
    attached = upload_audio(client, auth, source_y)
    assert attached.status_code == 201
    foreign_attachment = attached.json()['id']
    body = {
        'source_document_id': source_x, 'stem': '虚构测试数据：引用音频附件的题目',
        'kind': 'single_choice', 'options': ['A. 1', 'B. 2'], 'correct_answer': 'A',
        'knowledge_ids': ['math.arithmetic'], 'max_points': 2,
    }
    missing = client.post('/api/admin/questions', headers=auth,
                          json={**body, 'media_attachment_id': 'nonexistent-attachment'})
    assert missing.status_code == 422
    assert missing.json()['detail'] == 'MEDIA_ATTACHMENT_INVALID'
    cross_source = client.post('/api/admin/questions', headers=auth,
                               json={**body, 'media_attachment_id': foreign_attachment})
    assert cross_source.status_code == 422
    assert cross_source.json()['detail'] == 'MEDIA_ATTACHMENT_INVALID'

def test_revision_media_reference_validation(client, auth, private_dir):
    # Gate 整改回归：修订创建新版本，媒体引用同样须存在/同源/属 owner（§1）。
    # 原版题经 import-confirm 创建（源带附件时 ST-003 门禁禁止 admin 直建发布）。
    source_x = make_source(client, auth, 'english', '虚构测试数据：修订媒体校验题源')
    source_y = make_source(client, auth, 'english', '虚构测试数据：修订媒体校验异源')
    own_audio = upload_audio(client, auth, source_x)
    foreign_audio = upload_audio(client, auth, source_y)
    assert own_audio.status_code == 201 and foreign_audio.status_code == 201
    own_id = own_audio.json()['id']
    assert client.post(f'/api/admin/attachments/{own_id}/parse', headers=auth).status_code == 200
    confirmed = client.post(f'/api/admin/attachments/{own_id}/confirm', headers=auth, json={
        'confirmed_by_human': True,
        'questions': [{
            'source_document_id': source_x, 'stem': '虚构测试数据：原版听力题',
            'kind': 'single_choice', 'options': ['A. apple', 'B. banana'], 'correct_answer': 'A',
            'knowledge_ids': ['english.listening'], 'max_points': 1, 'media_attachment_id': own_id,
        }],
    })
    assert confirmed.status_code == 201
    version_id = confirmed.json()['question_version_ids'][0]
    assert review_source(client, auth, source_x).status_code == 201  # 上传附件后须重新审核来源
    assert client.post(f'/api/admin/questions/{version_id}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 200
    body = {
        'source_document_id': source_x, 'stem': '虚构测试数据：原版听力题',
        'kind': 'single_choice', 'options': ['A. apple', 'B. banana'], 'correct_answer': 'A',
        'knowledge_ids': ['english.listening'], 'max_points': 1, 'media_attachment_id': own_id,
    }
    path = f'/api/admin/questions/{version_id}/revisions'
    foreign = client.post(path, headers=auth,
                          json={**body, 'media_attachment_id': foreign_audio.json()['id']})
    assert foreign.status_code == 422 and foreign.json()['detail'] == 'MEDIA_ATTACHMENT_INVALID'
    missing = client.post(path, headers=auth,
                          json={**body, 'media_attachment_id': 'nonexistent-attachment'})
    assert missing.status_code == 422 and missing.json()['detail'] == 'MEDIA_ATTACHMENT_INVALID'
    valid = client.post(path, headers=auth, json=body)
    assert valid.status_code == 201 and valid.json()['version'] == 2
