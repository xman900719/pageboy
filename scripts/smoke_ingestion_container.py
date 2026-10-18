"""在隔离临时容器内验证 ST-003；执行方式见验收记录。"""
import os
from io import BytesIO
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont
assert os.environ.get("DATABASE_URL") == "sqlite+pysqlite:////tmp/st003.sqlite3", "仅允许本脚本专用容器临时库"
from shutong.private_files import validate_file, parse_text, write_blob, blob_path
from shutong.main import app
assert os.getuid() == 10001
import yaml
assert app.openapi() == yaml.safe_load(Path("/tmp/openapi.yaml").read_text())
assert app.openapi()['paths']['/api/admin/attachments/{attachment_id}/confirm']
subprocess.run(['alembic', 'upgrade', 'head'], check=True)
subprocess.run(['alembic', 'check'], check=True)
image = Image.new('RGB', (1000, 200), 'white')
ImageDraw.Draw(image).text((20,40), 'SYNTHETIC TEST DATA', fill='black', font=ImageFont.load_default(size=48))
for media, format in [('image/png','PNG'), ('image/jpeg','JPEG')]:
    output = BytesIO()
    image.save(output, format=format)
    data = output.getvalue()
    validate_file(data, media)
    text, version = parse_text(data, media)
    assert 'SYNTHETIC' in text.upper(), text
    key = write_blob(data)
    path = blob_path(key)
    assert path.read_bytes() == data and path.stat().st_mode & 0o777 == 0o600
    path.unlink()
    print('PASS: uid=10001 private write and real '+format+' OCR: '+version)
assert subprocess.run(['pdfinfo','-v'], capture_output=True).returncode == 0
assert subprocess.run(['pdftotext','-v'], capture_output=True).returncode == 0
print('PASS: Python 3.12 container imports, new routes, migrations and local parsers')
