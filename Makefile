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
	python scripts/test_st024b_gates.py
	python scripts/test_st024c_gates.py
	python scripts/test_web_artifact_provenance.py
openapi:
	python scripts/check_openapi.py
frontend-build:
	cd apps/web && npm run build
