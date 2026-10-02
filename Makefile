.PHONY: lint test

lint:                       ## ruff format --check, ruff check, ty
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check

test:                       ## Run the test suite with coverage
	uv run pytest --cov=keryx --cov-branch --cov-report=term-missing
