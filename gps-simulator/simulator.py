#!/usr/bin/env python3
"""GPS/telemetry simulator: drives a virtual vehicle and publishes to MQTT.

Demonstrates the flow: vehicle moving → MQTT message → backend consumer →
database → API. It writes nothing to the database itself; the backend is the
only writer.

Usage:
    python simulator.py                      # defaults from environment
    python simulator.py --device-id GPS-001 --vehicle-id <uuid> --interval 2.0

Environment variables (all optional):
    MQTT_BROKER_HOST   default 127.0.0.1
    MQTT_BROKER_PORT   default 1883
    MQTT_USERNAME      default empty
    MQTT_PASSWORD      default empty
    GPS_DEVICE_ID      default GPS-001
    GPS_VEHICLE_ID     default empty (topic falls back to "unknown"; set it in practice)
    GPS_START_LAT / GPS_START_LON   starting point (default Accra)
    GPS_INTERVAL_SECONDS  publish cadence, default 2.0
    GPS_SPEED_KPH      cruise speed, default 40

Movement model: a random-walk heading with speed noise and brief stops, with
slow battery drain, so a demo drive looks plausible. Stops cleanly on Ctrl+C.
"""

import argparse
import json
import math
import os
import random
import signal
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("paho-mqtt is required: pip install -r gps-simulator/requirements.txt")

# Rough spherical approximations, fine for a demo (not for navigation).
KM_PER_DEGREE_LAT = Decimal("111.32")
MQTT_HOST_DEFAULT = "127.0.0.1"
MQTT_PORT_DEFAULT = 1883


def env(name, default):
    return os.environ.get(name, default)


def env_float(name, default):
    try:
        return float(env(name, default))
    except ValueError:
        return default


class VehicleSim:
    """Random-walk movement with battery drain."""

    def __init__(self, device_id, vehicle_id, lat, lon, speed_kph):
        self.device_id = device_id
        self.vehicle_id = vehicle_id
        self.lat = Decimal(str(lat))
        self.lon = Decimal(str(lon))
        self.cruise_speed = Decimal(str(speed_kph))
        self.heading = random.uniform(0, 360)
        self.battery = 100

    def step(self, seconds):
        """Advance the vehicle by ``seconds`` and return the telemetry dict."""
        # Pick a fresh direction occasionally; drift slightly otherwise.
        if random.random() < 1 / 15:
            self.heading = random.uniform(0, 360)
        else:
            self.heading = (self.heading + random.uniform(-10, 10)) % 360
        speed = max(Decimal("0"), self.cruise_speed + Decimal(str(random.uniform(-8, 4))))
        if speed < 1:
            # Brief pause, then move again.
            speed = Decimal("0") if random.random() < 0.5 else self.cruise_speed

        distance_km = speed * Decimal(str(seconds)) / Decimal(3600)
        heading_rad = math.radians(self.heading)
        dlat = distance_km * Decimal(str(math.cos(heading_rad))) / KM_PER_DEGREE_LAT
        # Degrees of longitude shrink with latitude, not heading.
        km_per_degree_lon = KM_PER_DEGREE_LAT * Decimal(
            str(math.cos(math.radians(float(self.lat))))
        )
        dlon = (
            distance_km
            * Decimal(str(math.sin(heading_rad)))
            / max(Decimal("0.1"), km_per_degree_lon)
        )
        self.lat = (self.lat + dlat).quantize(Decimal("0.000001"))
        self.lon = (self.lon + dlon).quantize(Decimal("0.000001"))
        self.battery = max(0, self.battery - random.choice([0, 0, 1]))

        return {
            "device_id": self.device_id,
            "vehicle_id": self.vehicle_id or None,
            "latitude": float(self.lat),
            "longitude": float(self.lon),
            "speed": float(speed.quantize(Decimal("0.1"))),
            "heading": int(self.heading),
            "battery": self.battery,
            "ignition": True,
            "timestamp": datetime.now(UTC).isoformat(),
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Publish simulated GPS telemetry over MQTT.")
    parser.add_argument("--device-id", default=env("GPS_DEVICE_ID", "GPS-001"))
    parser.add_argument("--vehicle-id", default=env("GPS_VEHICLE_ID", ""))
    parser.add_argument("--broker-host", default=env("MQTT_BROKER_HOST", MQTT_HOST_DEFAULT))
    parser.add_argument(
        "--broker-port", type=int, default=int(env("MQTT_BROKER_PORT", MQTT_PORT_DEFAULT))
    )
    parser.add_argument("--username", default=env("MQTT_USERNAME", ""))
    parser.add_argument("--password", default=env("MQTT_PASSWORD", ""))
    parser.add_argument("--interval", type=float, default=env_float("GPS_INTERVAL_SECONDS", 2.0))
    parser.add_argument("--speed", type=float, default=env_float("GPS_SPEED_KPH", 40.0))
    parser.add_argument("--lat", type=float, default=env_float("GPS_START_LAT", 5.6037))
    parser.add_argument("--lon", type=float, default=env_float("GPS_START_LON", -0.1870))
    return parser.parse_args()


def main():
    args = parse_args()
    stop = {"flag": False}

    def request_stop(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{args.device_id}")
    if args.username:
        client.username_pw_set(args.username, args.password or None)

    topic = f"vehicles/{args.vehicle_id or 'unknown'}/telemetry"
    sim = VehicleSim(args.device_id, args.vehicle_id, args.lat, args.lon, args.speed)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"Connected to {args.broker_host}:{args.broker_port}; publishing to {topic}")
        else:
            print(f"Connection refused: {reason_code}", file=sys.stderr)

    def on_disconnect(client, userdata, flags, reason_code, properties):
        print("Disconnected from broker.", file=sys.stderr)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    try:
        client.connect(args.broker_host, args.broker_port, keepalive=60)
    except OSError as exc:
        sys.exit(f"Cannot reach broker at {args.broker_host}:{args.broker_port}: {exc}")
    client.loop_start()

    published = 0
    while not stop["flag"]:
        time.sleep(args.interval)
        payload = sim.step(args.interval)
        info = client.publish(topic, json.dumps(payload).encode(), qos=1)
        info.wait_for_publish(timeout=5)
        published += 1
        print(
            f"[{published:04d}] lat={payload['latitude']:.6f} lon={payload['longitude']:.6f} "
            f"speed={payload['speed']:.1f} battery={payload['battery']}%"
        )
    client.disconnect()
    client.loop_stop()
    print(f"Stopped after {published} messages.")


if __name__ == "__main__":
    main()
