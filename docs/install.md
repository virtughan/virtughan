## Installation and Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/)

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### As a Python Package

```bash
pip install virtughan
```

### Local Development Setup

```bash
git clone https://github.com/virtughan/virtughan.git
cd virtughan
just run
```

This installs dependencies and starts the dev server with hot reload.

For production:

```bash
uv run uvicorn API:app --host 0.0.0.0 --port 8080 --workers 2
```

### Docker

```bash
docker build -t virtughan .
docker run --rm -p 8080:8080 virtughan
```

### Configuration

All settings are configurable via environment variables. Copy the example and adjust:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `json` | `json` for production, `console` for development |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `RATE_LIMIT_DEFAULT` | `60/minute` | General endpoint rate limit |
| `RATE_LIMIT_EXPORT` | `10/minute` | Export/download rate limit |
| `RATE_LIMIT_TILE` | `120/minute` | Tile endpoint rate limit |
| `MAX_BBOX_AREA_SQ_DEG` | `25.0` | Maximum bounding box area in square degrees |
| `MAX_DATE_RANGE_DAYS` | `1825` | Maximum date range (5 years) |
| `REQUEST_TIMEOUT` | `120` | Request timeout in seconds |
| `EXPIRY_DURATION_HOURS` | `1` | Hours before export results are cleaned up |

### Development Tools

Lint, format, type check, and run pre-commit hooks:

```bash
just lint
```

Run tests:

```bash
just test
```
