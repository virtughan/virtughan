default:
    @just --list

install:
    uv sync

lint:
    uv run ruff check src/ tests/ --fix
    uv run ruff format src/ tests/
    uv run ty check src/

test:
    uv run pytest tests/

publish:
    uv build
    uv publish

bump part="patch":
    uv version --bump {{part}}
