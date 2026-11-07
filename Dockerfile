
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS dev

COPY pyproject.toml README.md constraints.txt ./
COPY src ./src
RUN pip install -c constraints.txt -e ".[dev]"

COPY alembic.ini ./
COPY migrations ./migrations
COPY tests ./tests

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS build

COPY pyproject.toml README.md constraints.txt ./
COPY src ./src
RUN pip wheel -c constraints.txt --wheel-dir /wheels .

FROM base AS prod

COPY --from=build /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels \
    && useradd --system --uid 10001 --no-create-home erp

COPY alembic.ini ./
COPY migrations ./migrations

USER erp

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM prod AS prod-ia

USER root
COPY constraints.txt ./
RUN pip install -c constraints.txt "scikit-learn" && rm constraints.txt
USER erp

CMD ["python", "-m", "app.workers.anomalias"]
