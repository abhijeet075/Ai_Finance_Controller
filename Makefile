.PHONY: api frontend test lint db-up db-down migrate generate-data test-ground-truth test-ingestion test-normalization

api:
	uvicorn app.main:app --app-dir backend --reload

frontend:
	cd frontend && npm run dev

test:
	pytest

lint:
	ruff check backend scripts
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
