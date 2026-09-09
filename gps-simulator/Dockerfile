# syntax=docker/dockerfile:1
# The simulator mirrors a GPS device: it only needs paho-mqtt and network
# access to a broker, which is why it is a separate tiny image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /sim
COPY gps-simulator/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY gps-simulator/simulator.py simulator.py

CMD ["python", "simulator.py"]
