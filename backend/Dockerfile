# syntax=docker/dockerfile:1.7
FROM python:3.12.14-slim-trixie AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip==26.2 \
    && python -m pip install --requirement /tmp/requirements.txt


FROM python:3.12.14-slim-trixie AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TAMILTROVE_ENV=production \
    TAMILTROVE_DATA_PATH=/app/data/movies_processed.json \
    TAMILTROVE_EMBEDDINGS_PATH=/app/data/embeddings.npy

RUN groupadd --gid 10001 tamiltrove \
    && useradd --uid 10001 --gid tamiltrove --create-home --shell /usr/sbin/nologin tamiltrove

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=tamiltrove:tamiltrove app ./app
COPY --chown=tamiltrove:tamiltrove migrations ./migrations
COPY --chown=tamiltrove:tamiltrove data ./data
COPY --chown=tamiltrove:tamiltrove main.py ./main.py

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--proxy-headers"]
