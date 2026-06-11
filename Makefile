.PHONY: help install dev run test cov lint fmt typecheck docker up down loadtest clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package
	pip install -e .

dev:  ## Install with dev + redis extras
	pip install -e ".[dev,redis]"

run:  ## Run the gateway (mock providers, no keys needed)
	kvgate run

test:  ## Run the test suite
	pytest

cov:  ## Run tests with coverage report
	pytest --cov=kvgate --cov-report=term-missing

lint:  ## Lint with ruff
	ruff check .

fmt:  ## Auto-format with ruff
	ruff format .

typecheck:  ## Type-check with mypy
	mypy src

docker:  ## Build the Docker image
	docker build -t kvgate:latest .

up:  ## Start the full stack (gateway + redis + prometheus + grafana)
	docker compose up --build

down:  ## Stop the stack
	docker compose down

loadtest:  ## Run the Locust load test (UI at http://localhost:8089)
	locust -f loadtest/locustfile.py --host http://localhost:8080

clean:  ## Remove build/test artifacts
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
