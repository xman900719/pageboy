#!/usr/bin/env python3
"""Real Draft 2020-12 validation, FormatChecker, and intentional failure cases."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / 'contracts' / 'schemas'
EXAMPLES = ROOT / 'contracts' / 'examples'

def validator(name: str):
    schema = json.loads((SCHEMA_DIR/name).read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def valid(v, obj):
    return not list(v.iter_errors(obj))

def check():
    items = [
        ("source-document.schema.json", "source.valid.json"),
        ("evidence.schema.json", "evidence.valid.json"),
        ("goal.schema.json", "goal.valid.json"),
        ("curriculum-standard-source.schema.json", "curriculum_source.valid.json"),
        ("curriculum-standard-clause.schema.json", "curriculum_clause.valid.json"),
    ]
    for schema_name, example_name in items:
        v=validator(schema_name)
        source=json.loads((EXAMPLES/example_name).read_text(encoding='utf-8'))
        assert valid(v,source), f"valid example incorrectly rejected: {schema_name}"
        invalid=copy.deepcopy(source)
        invalid["unexpected_field"] = "must be rejected"
        assert not valid(v, invalid), f"extra field incorrectly allowed: {schema_name}"
    v=validator('source-document.schema.json')
    src=json.loads((EXAMPLES/'source.valid.json').read_text(encoding='utf-8'))
    for field, bad in [('exam_year','2026'),('source_url','not a valid URL'),('sha256','bad-hash'),('rights_status','unlicensed'),('verified','true')]:
        example={**src,field:bad}
        assert not valid(v,example), f"INVALID {field} PASSED"
    v=validator('evidence.schema.json')
    evidence=json.loads((EXAMPLES/'evidence.valid.json').read_text(encoding='utf-8'))
    assert not valid(v,{**evidence,'earned_points':-1})
    assert not valid(v,{**evidence,'max_points':0})
    # JSON Schema has no portable property-to-property comparison; enforce semantic check here.
    assert evidence['earned_points'] <= evidence['max_points']
    v=validator('goal.schema.json')
    goal=json.loads((EXAMPLES/'goal.valid.json').read_text(encoding='utf-8'))
    assert not valid(v,{**goal,'target_points':'90'})
    assert goal['target_points'] <= goal['max_points']
    print('PASS: JSON Schema valid examples and deliberate invalid cases')

if __name__ == '__main__': check()
