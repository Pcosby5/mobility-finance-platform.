# syntax=docker/dockerfile:1
# Backend image used by both the web and telemetry-consumer Compose services.
# Code is baked into the image (prod parity) rather than bind-mounted, so what
# runs in a container is what will ship to Render.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl exists only for the container healthcheck on /api/health/.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 django

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

# Copy the backend package contents (manage.py, config/, apps) into /app.
COPY backend/ .
USER django

EXPOSE 8000
# Commands (migrate + server) are supplied by Compose/Render; the image stays
# a single artifact for both the web and consumer roles.
CMD ["python", "manage.py", "run_mqtt_consumer"]
