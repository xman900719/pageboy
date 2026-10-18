#!/usr/bin/env python3
"""Resolve local Markdown links/images using Markdown parsing (exclude fenced code)."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parents[1]
PARSER=MarkdownIt()


def check_markdown(path: Path, allowed_root: Path = ROOT) -> list[str]:
    problems=[]
    tokens=PARSER.parse(path.read_text(encoding='utf-8'))
    for token in tokens:
        for child in token.children or []:
            url=None
            if child.type=='image': url=child.attrGet('src')
            elif child.type=='link_open': url=child.attrGet('href')
            if not url or url.startswith(('#','mailto:','tel:')) or '://' in url: continue
            loc=unquote(urlsplit(url).path)
            if not loc: continue
            target=(path.parent / loc).resolve()
            try: target.relative_to(allowed_root.resolve())
            except ValueError:
                problems.append(f'{path.relative_to(allowed_root)}: path escapes repository: {url}')
                continue
            if not target.exists(): problems.append(f'{path.relative_to(allowed_root)}: missing local resource: {url}')
    return problems

def check():
    paths=list((ROOT/'docs').rglob('*.md')) + [ROOT/name for name in ['README.md','AGENTS.md','CONTRIBUTING.md','CODEX_START_HERE.md','IMPLEMENTATION_PLAN.md','PROJECT_STATUS.md','PROMPT_FOR_CODEX.md']]
    errors=[]
    for path in paths:
        errors += check_markdown(path)
    if errors: raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(paths)} Markdown files, local links and image assets')

if __name__=='__main__':check()
