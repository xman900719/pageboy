#!/usr/bin/env python3
"""Fail CI if committed OpenAPI snapshot differs from actual routes."""
from pathlib import Path
import sys, yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/api'))
from shutong.main import app
p=ROOT/'contracts/openapi.yaml'
assert p.is_file(), 'missing contracts/openapi.yaml'
expected=app.openapi()
actual=yaml.safe_load(p.read_text(encoding='utf-8'))
assert actual==expected, 'OpenAPI contract drift! Run python scripts/generate_openapi.py'
print('PASS: actual API == committed OpenAPI contract')
