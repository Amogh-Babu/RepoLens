PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
VENV_PYTEST := $(VENV)/bin/pytest
VENV_UVICORN := $(VENV)/bin/uvicorn

.PHONY: help setup build test test-backend test-frontend run run-backend run-frontend clean

help:
	@echo "RepoLens Build, Test & Run Commands:"
	@echo "  make setup          Create Python .venv and install backend & frontend dependencies"
	@echo "  make build          Install dependencies, compile backend, and build frontend bundle"
	@echo "  make test           Run all backend (pytest) and frontend (lint, typecheck, Vitest) checks"
	@echo "  make test-backend   Run the backend pytest suite"
	@echo "  make test-frontend  Run frontend ESLint, Prettier, TypeScript, and Vitest checks"
	@echo "  make run            Start both the FastAPI backend (:8000) and Vite frontend (:5173)"
	@echo "  make run-backend    Start only the FastAPI backend on http://127.0.0.1:8000"
	@echo "  make run-frontend   Start only the Vite dev server on http://localhost:5173"
	@echo "  make clean          Remove build artifacts and test caches"

setup:
	test -x $(VENV_PYTHON) || $(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install -r backend/requirements-dev.txt
	npm --prefix frontend ci

build: setup
	$(VENV_PYTHON) -m compileall -q backend/repolens
	npm --prefix frontend run build

test-backend:
	@test -x $(VENV_PYTEST) || (echo "Run 'make setup' or 'make build' first." && exit 1)
	$(VENV_PYTEST) -c backend/pyproject.toml backend/tests

test-frontend:
	npm --prefix frontend run lint
	npm --prefix frontend run format:check
	npm --prefix frontend run typecheck
	npm --prefix frontend test

test: test-backend test-frontend

run-backend:
	@test -x $(VENV_UVICORN) || (echo "Run 'make setup' or 'make build' first." && exit 1)
	PYTHONPATH=backend $(VENV_UVICORN) repolens.api.app:app --app-dir backend --host 127.0.0.1 --port 8000 --reload

run-frontend:
	npm --prefix frontend run dev

run:
	@test -x $(VENV_UVICORN) || (echo "Run 'make setup' or 'make build' first." && exit 1)
	@PYTHONPATH=backend $(VENV_UVICORN) repolens.api.app:app --app-dir backend --host 127.0.0.1 --port 8000 --reload & \
		BACKEND_PID=$$!; \
		trap 'kill $$BACKEND_PID 2>/dev/null || true' INT TERM EXIT; \
		npm --prefix frontend run dev

clean:
	rm -rf frontend/dist .pytest_cache backend/.pytest_cache
