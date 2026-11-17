FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 10001 ub

RUN mkdir -p /app/ub/modules /app/ub/data \
    && chown -R ub:ub /app/ub
COPY __init__.py /app/ub/__init__.py
COPY __main__.py /app/ub/__main__.py
COPY loader.py /app/ub/loader.py
COPY utils.py /app/ub/utils.py

USER ub
WORKDIR /app
HEALTHCHECK --interval=10s --timeout=3s --start-period=180s --retries=3 \
  CMD ["python", "-S", "-c", "from pathlib import Path; raise SystemExit(0 if Path('/tmp/ub-ready').is_file() else 1)"]
CMD ["python", "-m", "ub"]
