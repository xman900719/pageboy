from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location('check_docs',Path(__file__).parent/'check_docs.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_missing_image_is_detected(tmp_path):
    p=tmp_path/'sample.md';p.write_text('# Example\n![missing](not-found.png)\n',encoding='utf-8')
    assert any('not-found.png' in x for x in m.check_markdown(p, allowed_root=tmp_path))

def test_fenced_code_is_not_link(tmp_path):
    p=tmp_path/'sample.md';p.write_text('# Example\n```markdown\n![fake](missing.png)\n```\n',encoding='utf-8')
    assert m.check_markdown(p, allowed_root=tmp_path)==[]
