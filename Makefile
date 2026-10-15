PY := backend/.venv/bin/python
BACKEND := cd backend &&

.PHONY: setup reset seed dev api web test acceptance smoke smoke-cognee smoke-stripe phase1 phase2 billing-check pay-check phase6

setup: ## create the Python 3.12 venv and install backend + frontend dependencies
	uv python install 3.12
	$(BACKEND) uv sync --python 3.12
	cd frontend && npm install

reset: ## wipe SQLite and Cognee memory
	$(BACKEND) .venv/bin/python scripts/reset.py

seed: ## load demo data and run the pipeline (demo clock 2026-10-31 18:00)
	$(BACKEND) .venv/bin/python scripts/seed_demo.py

dev: ## API on :8000 and web on :5173
	@trap "kill 0" INT TERM EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --port 8000) & \
	(cd frontend && npm run dev -- --port 5173 --strictPort) & \
	wait

api:
	$(BACKEND) .venv/bin/uvicorn app.main:app --port 8000 --reload

web:
	cd frontend && npm run dev -- --port 5173 --strictPort

test: ## unit tests (no API keys needed)
	$(BACKEND) .venv/bin/python -m pytest -q

acceptance: ## PLAN.md section 13 (needs LLM_API_KEY)
	$(BACKEND) .venv/bin/python scripts/acceptance.py

smoke: smoke-cognee smoke-stripe ## Phase 0 smoke tests
smoke-cognee:
	$(BACKEND) .venv/bin/python scripts/smoke_cognee.py
smoke-stripe:
	$(BACKEND) .venv/bin/python scripts/smoke_stripe.py

phase1:
	$(BACKEND) .venv/bin/python scripts/phase_checks.py phase1
phase2:
	$(BACKEND) .venv/bin/python scripts/phase_checks.py phase2
billing-check: ## Phase 4: jump to 1 Nov 09:00 and verify the Stripe invoice
	$(BACKEND) .venv/bin/python scripts/billing_check.py
pay-check: ## Phase 4: same, and pay it with the Stripe test card through the API
	$(BACKEND) .venv/bin/python scripts/billing_check.py --pay
phase6: ## proof link + disputes
	$(BACKEND) .venv/bin/python scripts/phase_checks.py phase6
