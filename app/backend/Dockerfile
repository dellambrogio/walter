FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml ./
RUN mkdir walter && touch walter/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"

COPY . .

CMD ["sh", "-c", "alembic upgrade head && uvicorn walter.main:app --host 0.0.0.0 --port 8000"]
