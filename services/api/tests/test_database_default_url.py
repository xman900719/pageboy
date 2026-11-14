import subprocess
import sys
from pathlib import Path

from shutong.database import DEFAULT_DATABASE_URL
from shutong.home import default_sqlite_path


def test_default_url_is_absolute_and_under_pageboy_home():
    path = Path(DEFAULT_DATABASE_URL.split(":///", 1)[1])
    assert path.is_absolute()
    assert path == default_sqlite_path()
    assert path.parts[-3:] == ("development", "data", "shutong-dev.sqlite3")


def test_default_url_independent_of_cwd(tmp_path):
    out = subprocess.run(
        [sys.executable, "-c", "from shutong.database import DEFAULT_DATABASE_URL as u; print(u)"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == DEFAULT_DATABASE_URL
