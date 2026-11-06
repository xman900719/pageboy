.PHONY: verify api-test contracts docs openapi frontend-build diagrams
verify: api-test contracts docs openapi
api-test:
	cd services/api && python -m pytest -q
contracts:
	python scripts/validate_contracts.py
diagrams:
	node scripts/render_diagrams.mjs
docs: diagrams
	python scripts/check_docs.py
	python -m pytest scripts/test_docs_checker.py -q
openapi:
	python scripts/check_openapi.py
frontend-build:
	cd apps/web && npm run build
