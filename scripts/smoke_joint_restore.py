#!/usr/bin/env python3
"""ST-OPS-01 本地隔离恢复演练（LOCAL DRILL ONLY——不是 AC-OPS-01）。

本机闭环验证「联合备份 → 摧毁 → 隔离恢复 → 冒烟」：
  A 首次部署：仅起 compose db 服务（127.0.0.1 随机发布口）+ 本地 uvicorn:18765，
    经管理 API 种子（全部虚构测试数据）：普通单选题 + 合成 mp3 听力题
    （upload→parse→confirm-import→来源复审→审核→发布）+ 一次练习 next/attempt；
    记录 psql 行数与附件 sha256。
  B 联合备份：本地演练模式跑 infra/backup.sh（BACKUP_OUTPUT_DIR 置位即跳过 restic），
    校验 postgres.dump + attachments.tar.gz + 双文件 SHA256SUMS + manifest。
  C 摧毁：compose down -v 删卷、删除附件目录——原部署不复存在。
  D 恢复：全新 compose db（新项目名/新卷/新口）+ infra/restore.sh（含两条拒绝反例），
    再起 uvicorn:18766 连恢复库与恢复附件目录。
  E 冒烟：行数、迁移版本、附件元数据/字节、next、作答溯源逐项比对 Phase A 记录。

诚实边界：本地演练 ≠ 异地备份；3-2-1 的"另一故障域"未验证，不宣称 AC-OPS-01 与任何
RPO/RTO。restic 未安装，生产 restic 路径本机无法实测。宿主 8000 被无关常驻服务占用，
本演练只使用 127.0.0.1 随机口 + 18765/18766，绝不触碰 8000 或任何非本演练创建的进程。
"""
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / 'services/api'
TOKEN = 'st-ops-01-local-drill-secret'
APP_REVISION = 'st-ops-01-local-drill'
COUNT_TABLES = ('source_documents', 'questions', 'question_versions', 'exposures', 'answer_attempts', 'source_attachments')
EXPECTED_COUNTS = {'source_documents': 2, 'questions': 2, 'question_versions': 2,
                   'exposures': 1, 'answer_attempts': 1, 'source_attachments': 1}
DB_USER = 'pageboy_drill'


def evidence(message):
    print(f'[ST-OPS-01-LOCAL] {message}', flush=True)


def run(cmd, cwd=ROOT, env=None, capture=True):
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=capture, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'命令失败 rc={result.returncode}: {" ".join(map(str, cmd))}\n'
                            f'stderr={result.stderr[-800:]}\nstdout={result.stdout[-800:]}')
    return result


def run_output(cmd, cwd=ROOT, env=None):
    result = run(cmd, cwd=cwd, env=env)
    return result.stdout.strip()


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def repo_head():
    return run_output([sys.executable, '-m', 'alembic', 'heads'], cwd=API_DIR).split()[0]


def api(base, path, method='GET', body=None):
    """JSON 管理端点调用（Bearer 令牌）；非 2xx 直接失败并带响应体。"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'{method} {path} -> HTTP {error.code}: {error.read().decode(errors="replace")[:300]}') from None
    return json.loads(payload) if payload else None


def api_raw(base, path, method='GET', data=None, content_type=None):
    headers = {'Authorization': f'Bearer {TOKEN}'}
    if content_type:
        headers['Content-Type'] = content_type
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'{method} {path} -> HTTP {error.code}: {error.read().decode(errors="replace")[:300]}') from None


class ComposeDB:
    """仅 db 服务：项目隔离 + 一次性发布回环口；down -v 连卷一起清。"""

    def __init__(self, project, db_name, password, workdir):
        self.project = project
        self.db_name = db_name
        self.password = password
        self.port = free_port()
        self.env_file = workdir / f'{project}.env'
        self.override = workdir / f'{project}-ports.yaml'
        self.env_file.write_text(
            f'POSTGRES_USER={DB_USER}\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB={db_name}\nCOMPOSE_PROJECT_NAME={project}\n'
            # compose 插值会扫描全部服务（含未启动的 api），故须补齐 SHUTONG_TOKEN，值仅供本演练。
            f'SHUTONG_TOKEN={TOKEN}\n')
        # 演注：本机 registry 代理不可用、仅有 postgres:16 本地镜像——演练 override 固定该 tag
        # 只为让演练可运行；生产行为仍以 infra/compose.yaml（postgres:16-alpine）为准。
        self.override.write_text(
            f'services:\n  db:\n    image: postgres:16\n    ports:\n      - "127.0.0.1:{self.port}:5432"\n')

    def cmd(self, *args):
        return ['docker', 'compose', '-p', self.project, '--env-file', str(self.env_file),
                '-f', str(ROOT / 'infra/compose.yaml'), '-f', str(self.override), *args]

    def up(self):
        run(self.cmd('up', '-d', 'db'))
        # 就绪探测必须走发布口：容器内 unix socket 的 pg_isready 可能命中官方镜像
        # 首次初始化期间的"临时 server"（只听 unix socket），是虚假就绪（2026-10-22 实测踩坑）。
        deadline = time.monotonic() + 90
        last_error = ''
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(self.dsn(), connect_timeout=3):
                    pass
                evidence(f'compose db ready via published port: project={self.project} db={self.db_name} loopback port={self.port}')
                return
            except psycopg.OperationalError as error:
                last_error = str(error).strip()[:200]
                time.sleep(1)
        raise RuntimeError(f'compose db {self.project} 在 90 秒内未就绪：{last_error}')

    def dsn(self):
        return f'host=127.0.0.1 port={self.port} user={DB_USER} password={self.password} dbname={self.db_name}'

    def psql(self, sql):
        return run_output(self.cmd('exec', '-T', 'db', 'psql', '-U', DB_USER, '-d', self.db_name, '-t', '-A', '-c', sql))

    def row_counts(self):
        return {table: int(self.psql(f'SELECT count(*) FROM {table}')) for table in COUNT_TABLES}

    def database_url(self, driver='postgresql+psycopg'):
        return f'{driver}://{DB_USER}:{self.password}@127.0.0.1:{self.port}/{self.db_name}'

    def down(self):
        subprocess.run(self.cmd('down', '-v', '-t', '5'), capture_output=True, timeout=120)
        evidence(f'compose project down -v: {self.project}')


class ApiServer:
    def __init__(self, port, database_url, private_dir, workdir):
        self.base = f'http://127.0.0.1:{port}'
        self.log_path = workdir / f'uvicorn-{port}.log'
        self.log = open(self.log_path, 'wb')
        env = dict(os.environ, DATABASE_URL=database_url, SHUTONG_TOKEN=TOKEN,
                   SHUTONG_PRIVATE_DIR=str(private_dir), PYTHONPATH=str(API_DIR))
        self.proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'shutong.main:app',
                                      '--host', '127.0.0.1', '--port', str(port)],
                                     cwd=API_DIR, env=env, stdout=self.log, stderr=subprocess.STDOUT)

    def wait_ready(self):
        deadline = time.monotonic() + 60
        problems = []
        while time.monotonic() < deadline:
            try:
                if api(self.base, '/health/ready') == {'status': 'ready'}:
                    evidence(f'API ready at {self.base}')
                    return
            except (RuntimeError, OSError, urllib.error.URLError) as error:
                problems.append(str(error)[:120])
            time.sleep(0.5)
        raise RuntimeError(f'API 在 60 秒内未就绪：{problems[-3:]}；日志末尾：'
                           f'{self.log_path.read_text(errors="replace")[-500:]}')

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.log.close()
        evidence(f'API stopped at {self.base}')


def seed(base):
    """经管理 API 种子（全部虚构测试数据），返回 Phase A 记录。"""
    review = {'exam_year': 2026, 'source_url': 'https://example.org/synthetic-st-ops-01.pdf',
              'acquired_at': '2026-10-22', 'rights_status': 'licensed',
              'rights_basis': '虚构测试数据：合成题，人工确认无版权限制', 'applicable': True,
              'applicability_note': '虚构测试数据：适用于 ST-OPS-01 本地恢复演练', 'reviewed_by_human': True}
    source_a = api(base, '/api/admin/sources', 'POST', {
        'title': '虚构测试数据：ST-OPS-01 本地演练题源 A', 'subject': 'math',
        'rights_status': 'licensed', 'verified': True})['id']
    api(base, f'/api/admin/sources/{source_a}/review', 'POST', review)
    plain = api(base, '/api/admin/questions', 'POST', {
        'source_document_id': source_a, 'stem': '虚构测试数据：联合恢复演练单选题 1+1=?',
        'kind': 'single_choice', 'options': ['A. 1', 'B. 2'], 'correct_answer': 'A',
        'knowledge_ids': ['math.drill'], 'max_points': 2})
    api(base, f'/api/admin/questions/{plain["id"]}/review', 'POST')
    api(base, f'/api/admin/questions/{plain["id"]}/publish', 'POST')

    # 题源 B + 合成 mp3（ID3 魔数 + 零填充，无真实音频内容）：镜像 global-setup.ts 导入链。
    source_b = api(base, '/api/admin/sources', 'POST', {
        'title': '虚构测试数据：ST-OPS-01 本地演练听力题源 B', 'subject': 'math',
        'rights_status': 'licensed', 'verified': True})['id']
    mp3 = b'ID3\x03\x00\x00\x00' + bytes(500)
    upload_path = f'/api/admin/sources/{source_b}/attachments?{urllib.parse.urlencode({"filename": "虚构测试数据-听力.mp3"})}'
    attachment_id = json.loads(api_raw(base, upload_path, 'POST', data=mp3, content_type='audio/mpeg'))['id']
    api(base, f'/api/admin/attachments/{attachment_id}/parse', 'POST')
    confirmed = api(base, f'/api/admin/attachments/{attachment_id}/confirm', 'POST', {
        'confirmed_by_human': True, 'questions': [{
            'source_document_id': source_b, 'stem': '虚构测试数据：听力题——听录音选出提到的词。',
            'kind': 'single_choice', 'options': ['A. 甲', 'B. 乙'], 'correct_answer': 'A',
            'knowledge_ids': ['math.listen'], 'max_points': 2, 'media_attachment_id': attachment_id}]})
    listening_version = confirmed['question_version_ids'][0]
    # 上传令 source.verified 复位：重走来源审核，再审核并发布听力题。
    api(base, f'/api/admin/sources/{source_b}/review', 'POST', review)
    api(base, f'/api/admin/questions/{listening_version}/review', 'POST')
    api(base, f'/api/admin/questions/{listening_version}/publish', 'POST')

    nxt = api(base, '/api/practice/next?subject=math&knowledge_id=math.drill&purpose=training')
    attempt = api(base, '/api/practice/attempts', 'POST', {
        'client_attempt_id': 'st-ops-01-drill-attempt-001', 'exposure_id': nxt['exposure_id'],
        'answer': 'A', 'hints_used': False})
    meta = api(base, f'/api/admin/attachments/{attachment_id}')
    audio = api_raw(base, f'/api/admin/attachments/{attachment_id}/download')
    record = {'counts': None, 'attachment_id': attachment_id,
              'attachment_sha256': meta['sha256'], 'attachment_byte_size': meta['byte_size'],
              'audio_sha256': sha256(audio).hexdigest(),
              'next_stem': nxt['stem'], 'next_version_id': nxt['question_version_id'],
              'attempt_id': attempt['id'], 'scoring_origin': attempt['scoring_origin']}
    evidence(f'seeded sources=2 questions=2 published=2 attachment={attachment_id} '
             f'sha256={record["attachment_sha256"]} bytes={record["attachment_byte_size"]}')
    evidence(f'practice next served: {record["next_stem"]} (version {record["next_version_id"]}); '
             f'attempt={record["attempt_id"]} scoring_origin={record["scoring_origin"]}')
    return record


def run_backup(workdir, primary, attachments_dir, backup_dir):
    backup_env = dict(os.environ, ENV_FILE=str(primary.env_file),
                      BACKUP_OUTPUT_DIR=str(backup_dir), ATTACHMENTS_DIR=str(attachments_dir),
                      APP_REVISION=APP_REVISION)  # MIGRATION_REVISION 不设：实测自动探测路径
    result = run(['bash', str(ROOT / 'infra/backup.sh')], env=backup_env)
    evidence('backup.sh (local drill mode) stdout/stderr:')
    print(result.stdout.strip() or '(empty)', flush=True)
    print(result.stderr.strip() or '(empty)', flush=True)
    dump, tarball = backup_dir / 'postgres.dump', backup_dir / 'attachments.tar.gz'
    if not dump.is_file() or dump.stat().st_size == 0:
        raise RuntimeError('backup missing postgres.dump')
    if not tarball.is_file():
        raise RuntimeError('backup missing attachments.tar.gz')
    sums = (backup_dir / 'SHA256SUMS').read_text().splitlines()
    manifest = dict(line.split('=', 1) for line in (backup_dir / 'manifest.txt').read_text().splitlines())
    if len(sums) != 2 or not any('attachments.tar.gz' in line for line in sums) or not any('postgres.dump' in line for line in sums):
        raise RuntimeError(f'SHA256SUMS 未同时覆盖两个工件: {sums}')
    head = repo_head()
    if manifest.get('attachments_included') != 'yes':
        raise RuntimeError(f'manifest attachments_included={manifest.get("attachments_included")!r}（期望 yes）')
    if manifest.get('attachment_count') != '1':
        raise RuntimeError(f'manifest attachment_count={manifest.get("attachment_count")!r}（期望 1）')
    if manifest.get('migration_revision') != head:
        raise RuntimeError(f'manifest migration_revision={manifest.get("migration_revision")!r} != repo head {head}')
    if manifest.get('app_revision') != APP_REVISION:
        raise RuntimeError(f'manifest app_revision={manifest.get("app_revision")!r}（期望 {APP_REVISION}）')
    if 'T' not in manifest.get('timestamp_utc', '') or not manifest['timestamp_utc'].endswith('Z'):
        raise RuntimeError(f'manifest timestamp_utc 异常: {manifest.get("timestamp_utc")!r}')
    evidence(f'backup artifacts OK: postgres.dump={dump.stat().st_size}B attachments.tar.gz={tarball.stat().st_size}B '
             f'SHA256SUMS=2 files manifest(migration_revision={manifest["migration_revision"]}, attachments_included=yes, attachment_count=1)')


def run_restore(backup_dir, database_url, attachments_dir, expect_failure=False):
    # 本机 registry 代理不可用：restore 用的 pg_restore 镜像同样固定为本地已有的 postgres:16。
    restore_env = dict(os.environ, PG_RESTORE_IMAGE='postgres:16')
    result = subprocess.run(['bash', str(ROOT / 'infra/restore.sh'), '--backup-dir', str(backup_dir),
                            '--database-url', database_url, '--attachments-dir', str(attachments_dir)],
                            cwd=ROOT, env=restore_env, capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    if expect_failure:
        if result.returncode == 0 or 'REFUSED' not in output:
            raise RuntimeError(f'恢复脚本未按预期拒绝：rc={result.returncode} output={output[:300]}')
        evidence(f'guard refused as expected: {output.splitlines()[-1]}')
        return output
    if result.returncode != 0:
        raise RuntimeError(f'restore.sh 失败 rc={result.returncode}: {output[-500:]}')
    evidence('restore.sh OK: ' + ' | '.join(line for line in output.splitlines() if 'migration_revision' in line or 'Attachments restored' in line or 'pg_restore finished' in line))
    return output


def main():
    run_id = uuid4().hex[:8]
    workdir = Path('/tmp/opencode') / f'st_ops_drill_{run_id}'
    workdir.mkdir(parents=True)
    password = secrets.token_hex(24)
    primary_attachments = workdir / 'attachments-primary'
    restored_attachments = workdir / 'attachments-restored'
    backup_dir = workdir / 'backup'
    databases, servers = [], []
    try:
        head = repo_head()
        evidence(f'drill run dir={workdir} repo alembic head={head}')

        # ---- Phase A：首次部署 + 种子 + 记录 ----
        primary = ComposeDB(f'st_ops_drill_{run_id}', 'pageboy_drill_primary', password, workdir)
        databases.append(primary)
        primary.up()
        run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=API_DIR,
            env=dict(os.environ, DATABASE_URL=primary.database_url()))
        server = ApiServer(18765, primary.database_url(), primary_attachments, workdir)
        servers.append(server)
        server.wait_ready()
        record = seed(server.base)
        record['counts'] = primary.row_counts()
        if record['counts'] != EXPECTED_COUNTS:
            raise RuntimeError(f'Phase A 行数与种子预期不符: {record["counts"]} != {EXPECTED_COUNTS}')
        evidence(f'Phase A row counts: {record["counts"]}')
        blobs = [p for p in primary_attachments.iterdir()] if primary_attachments.exists() else []
        if len(blobs) != 1:
            raise RuntimeError(f'附件目录应恰有 1 个 blob，实际 {len(blobs)}')
        evidence(f'Phase A attachments dir: {len(blobs)} file(s), on-disk sha256={sha256(blobs[0].read_bytes()).hexdigest()}')

        # ---- Phase B：联合备份（本地演练模式）----
        run_backup(workdir, primary, primary_attachments, backup_dir)

        # ---- Phase C：摧毁原部署 ----
        server.stop()
        primary.down()
        shutil.rmtree(primary_attachments)
        leftover_containers = run_output(primary.cmd('ps', '-q', 'db')) or '0'
        if primary_attachments.exists() or int(leftover_containers) != 0:
            raise RuntimeError('Phase C 摧毁失败：附件目录或 db 容器仍存在')
        evidence('Phase C destroyed: primary compose project down -v, attachments dir deleted')

        # ---- Phase D：全新库 + 恢复（先跑两条拒绝反例）----
        restored = ComposeDB(f'st_ops_drill_{run_id}_r', 'pageboy_drill_restore', password, workdir)
        databases.append(restored)
        restored.up()
        guard_dir = workdir / 'guard-attachments'
        guard_dir.mkdir()
        (guard_dir / 'existing.txt').write_text('x')
        run_restore(backup_dir, f'postgres://{DB_USER}:{password}@127.0.0.1:1/not_pageboy_db', restored_attachments, expect_failure=True)
        run_restore(backup_dir, restored.database_url('postgres'), guard_dir, expect_failure=True)
        run_restore(backup_dir, restored.database_url('postgres'), restored_attachments)
        server2 = ApiServer(18766, restored.database_url(), restored_attachments, workdir)
        servers.append(server2)
        server2.wait_ready()

        # ---- Phase E：冒烟比对（行数检查先行，避免 next 落新曝光行）----
        failures = []
        counts = restored.row_counts()
        if counts != record['counts']:
            failures.append(f'row counts {counts} != Phase A {record["counts"]}')
        else:
            evidence(f'Phase E row counts equal Phase A: {counts}')
        revision = restored.psql('SELECT version_num FROM alembic_version')
        if revision != head:
            failures.append(f'restored alembic revision {revision!r} != repo head {head!r}')
        else:
            evidence(f'restored alembic revision == repo head: {revision}')
        meta = api(server2.base, f'/api/admin/attachments/{record["attachment_id"]}')
        if meta['sha256'] != record['attachment_sha256'] or meta['byte_size'] != record['attachment_byte_size']:
            failures.append(f'attachment metadata mismatch: {meta["sha256"]}/{meta["byte_size"]}')
        else:
            evidence(f'attachment metadata matches: sha256={meta["sha256"]} byte_size={meta["byte_size"]}')
        audio = api_raw(server2.base, f'/api/admin/attachments/{record["attachment_id"]}/download')
        audio_sha = sha256(audio).hexdigest()
        if audio_sha != record['audio_sha256'] or audio_sha != meta['sha256']:
            failures.append(f'download bytes differ: {audio_sha} != {record["audio_sha256"]}')
        else:
            evidence(f'download byte-identical: sha256={audio_sha}')
        nxt = api(server2.base, '/api/practice/next?subject=math&knowledge_id=math.drill&purpose=training')
        if nxt['question_version_id'] != record['next_version_id'] or nxt['stem'] != record['next_stem']:
            failures.append(f'practice next mismatch: {nxt}')
        else:
            evidence(f'practice next serves the seeded question: {nxt["stem"]}')
        attempts = api(server2.base, '/api/practice/attempts?subject=math')
        restored_attempt = next((a for a in attempts if a['id'] == record['attempt_id']), None)
        if restored_attempt is None or restored_attempt['scoring_origin'] != record['scoring_origin']:
            failures.append(f'attempt {record["attempt_id"]} not found or scoring_origin differs: {restored_attempt}')
        else:
            evidence(f'attempt restored with scoring_origin={restored_attempt["scoring_origin"]}')
        if failures:
            raise RuntimeError('Phase E 冒烟失败：\n- ' + '\n- '.join(failures))

        evidence('=' * 72)
        evidence('DRILL PASSED (LOCAL ONLY).')
        evidence('NOT AC-OPS-01: 异地/另一故障域备份、restic 生产路径、保留策略与告警均未验证；不宣称任何 RPO/RTO。')
        return 0
    finally:
        for server in servers:
            server.stop()
        for database in databases:
            database.down()
        shutil.rmtree(workdir, ignore_errors=True)
        evidence(f'cleanup done: compose projects removed, uvicorn stopped, {workdir.name} deleted')


if __name__ == '__main__':
    raise SystemExit(main())
