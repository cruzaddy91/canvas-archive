# Portable Makefile. Bash (not zsh) so it runs on Linux CI and macOS alike.
# uv-based rather than a plain venv, matching this repo's existing uv.lock
# and README quick start rather than diverging from it.
SHELL := /bin/bash

.PHONY: help install test lint clean

help:
	@echo "make install -- uv sync with dev extras (pytest, ruff)"
	@echo "make test    -- run the test suite"
	@echo "make lint    -- run ruff"
	@echo "make clean   -- remove caches and build artifacts"

install:
	uv sync --extra dev

test:
	uv run pytest

lint:
	uv run ruff check .

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
