FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system zeus && adduser --system --ingroup zeus zeus

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

EXPOSE 8000

FROM base AS dev

RUN pip install ".[dev]"
COPY tests ./tests
RUN chown zeus:zeus /app

USER zeus

CMD ["python", "-m", "pytest", "-q"]

FROM base AS runtime

USER zeus

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
