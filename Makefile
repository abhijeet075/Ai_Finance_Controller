.PHONY: api frontend test lint db-up db-down migrate generate-data \
	test-ground-truth test-ingestion test-normalization test-reconciliation \
	test-evaluation test-run-management

api:
	uvicorn app.main:app --app-dir backend --reload

frontend:
	cd frontend && npm run dev

test:
	pytest

lint:
	ruff check backend scripts evaluation
	cd frontend && npm run lint

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	alembic -c backend/alembic.ini upgrade head

generate-data:
	python scripts/generate_data.py --all-presets --seed 42 --clean

test-ground-truth:
	python -m unittest backend.tests.test_ground_truth -v

test-ingestion:
	PYTHONPATH=backend python -m unittest backend.tests.test_ingestion -v

test-normalization:
	PYTHONPATH=backend python -m unittest backend.tests.test_normalization -v

test-reconciliation:
	PYTHONPATH=.:backend python -m pytest \
		backend/tests/test_decision_engine.py \
		backend/tests/test_reconciliation_service.py \
		backend/tests/test_run_scoreboard.py -v

test-evaluation:
	PYTHONPATH=.:backend python -m pytest \
		backend/tests/test_ground_truth.py \
		backend/tests/test_phase11_evaluation.py \
		backend/tests/test_run_scoreboard.py -v

test-run-management:
	PYTHONPATH=.:backend python -m pytest \
		backend/tests/test_reconciliation_service.py \
		backend/tests/test_run_management.py \
		backend/tests/test_api_contracts.py -v
