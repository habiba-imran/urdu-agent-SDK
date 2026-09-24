FROM python:3.12.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VENV_PATH=/opt/venv

WORKDIR /app

RUN python -m venv "$VENV_PATH"
ENV PATH="$VENV_PATH/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.12.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    MALLOC_TRIM_THRESHOLD_=100000 \
    VENV_PATH=/opt/venv \
    PATH="/opt/venv/bin:$PATH"


WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY . .

# F-M9: run as a non-root user. F-H16: the COPY . . above now honours .dockerignore, so
# .git/, tests/ and docs/ no longer land in the runtime layer.
RUN useradd --system --create-home --uid 10001 uva && chown -R uva:uva /app
USER uva

# F-M25: worker/health_http.py serves /healthz when UVA_WORKER_HEALTH_PORT is set.
# Habiba owns wiring the Render probe; this makes the container self-report when enabled.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \n  CMD python -c "import os,sys,urllib.request; port=os.environ.get('UVA_WORKER_HEALTH_PORT'); sys.exit(0) if not port else sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=3).status==200 else 1)"

CMD ["python", "-m", "worker.main", "start"]
