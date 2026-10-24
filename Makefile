.PHONY: setup db migrate seed backend frontend test test-backend test-frontend e2e e2e-review
PY ?= python3

setup:
	cd backend && $(PY) -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && npm install

db:
	docker compose up -d db

migrate:
	cd backend && .venv/bin/alembic upgrade head

seed:
	cd backend && .venv/bin/python -m app.scripts.seed

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test-backend:
	cd backend && .venv/bin/python -m pytest

test-frontend:
	cd frontend && npm run typecheck && npm test

test: test-backend test-frontend

e2e:
	node scripts/e2e_live.mjs

e2e-review:
	node scripts/e2e_review.mjs
