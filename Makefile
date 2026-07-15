.PHONY: gate gate0 test lint db-sync usage fixtures secrets rls-check bundle-check
BASH := C:/Progra~1/Git/bin/bash.exe
PY := python
gate: secrets lint test rls-check usage-check
	@echo "GATE: PASS"

gate0:
	@$(BASH) scripts/gate0.sh
test:
	@pytest -q --tb=short
lint:
	@$(PY) -m ruff check . && $(PY) -m ruff format --check . && (cd sdk 2>/dev/null && npm run lint || true)
secrets:
	@$(BASH) -c 'gitleaks detect --no-banner --redact -v 2>/dev/null || { echo "GATE FAIL: secrets"; exit 1; }'
	@$(BASH) -c '! git ls-files | grep -qE '"'"'^\.env'"'"' || { echo "GATE FAIL: .env tracked"; exit 1; }'
rls-check:
	@$(PY) scripts/rls_check.py
usage-check:
	@$(PY) scripts/usage_guard.py
usage:
	@$(PY) scripts/usage_guard.py --report
db-sync:
	@echo "Run db-inspector subagent. Never hand-edit supabase/SCHEMA.md."
fixtures:
	@$(PY) scripts/fixture_stats.py
bundle-check:
	@cd sdk && npm run build && $(BASH) -c '! grep -rEq "(API_KEY|SECRET|SERVICE_ROLE|Bearer )" dist/ || { echo "GATE FAIL: secret in bundle"; exit 1; }'
