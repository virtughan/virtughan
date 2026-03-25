## docker build -t virtughan . && docker run --rm --name virtughan -p 8080:8080 virtughan

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen --no-dev --extra api

COPY . .

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "API:app", "--host", "0.0.0.0", "--port", "8080"]
