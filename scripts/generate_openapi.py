#!/usr/bin/env python3
"""Generate the canonical API snapshot from FastAPI routing without manual copies."""
from pathlib import Path
import sys
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/api'))
from shutong.main import app
output=ROOT/'contracts/openapi.yaml'
output.write_text(yaml.safe_dump(app.openapi(),allow_unicode=True,sort_keys=True),encoding='utf-8')
print(f'generated {output}')
