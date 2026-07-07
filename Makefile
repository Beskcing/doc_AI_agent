.PHONY: install lint test run dev clean migrate

install:
	pip install -e ".[dev]"

lint:
	ruff check src/

test:
	pytest tests/unit/ tests/integration/ -v

run:
	python -m scripts.run_server --port 8000

dev:
	cd frontend && npm run dev

migrate:
	alembic upgrade head

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
