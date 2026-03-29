default:
    @just --list

install:
    uv sync --extra api

run:
    uv sync --extra api
    uv run uvicorn API:app --reload

lint:
    uv run ruff check src/ tests/ API.py --fix
    uv run ruff format src/ tests/ API.py
    uv run ty check src/
    uv run pre-commit run --all-files

test:
    uv run pytest tests/

publish:
    uv build
    uv publish

bump part="patch":
    uv version --bump {{part}}
