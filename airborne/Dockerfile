FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --requirement requirements.txt \
    && addgroup --system airborne \
    && adduser --system --ingroup airborne airborne

COPY --chown=airborne:airborne airborne/airborne_bridge.py .

USER airborne

ENTRYPOINT ["python", "/app/airborne_bridge.py"]