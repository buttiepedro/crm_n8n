# ── Etapa 1: dependencias con uv ─────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# ── Etapa 2: runtime slim, usuario no root ────────────────────────────────
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN useradd --create-home appuser \
    && mkdir -p /data/storage \
    && chown -R appuser:appuser /data/storage

COPY --from=builder --chown=appuser:appuser /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
