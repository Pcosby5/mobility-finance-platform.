"""Run the MQTT telemetry consumer as a long-lived process.

Why a separate process: the broker connection is stateful and long-lived, so it
must never live inside Django's request/response workers — a broker outage or a
slow message burst must not affect HTTP latency, and a web redeploy must not
drop the subscription. Locally this is simply ``python manage.py
run_mqtt_consumer`` next to ``runserver``; the container entrypoint (Phase 6)
runs it as its own service, and in production the same consumer targets AWS
IoT Core instead of Mosquitto.

Error policy: malformed or unknown-device messages are logged and discarded
(they are device faults, not transport faults). Broker errors use bounded
exponential backoff on the initial connect, and paho's internal reconnect with
resubscribe afterwards. Ctrl+C / SIGTERM shut down cleanly.
"""

import logging
import signal
import time

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand

from telemetry.services import process_message

logger = logging.getLogger(__name__)

TOPIC_FILTER = "vehicles/+/telemetry"


class Command(BaseCommand):
    help = "Consume vehicle telemetry from the MQTT broker."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="Exit after processing the first message."
        )

    def handle(self, *args, **options):
        self.run_once = options["once"]
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="telemetry-consumer")
        if settings.MQTT_USERNAME:
            client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD or None)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        # SIGTERM should behave like Ctrl+C so supervisors stop us cleanly.
        signal.signal(signal.SIGTERM, self._request_stop)

        backoff = 1
        while True:
            try:
                client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, keepalive=60)
            except OSError as exc:
                self.stderr.write(f"Broker connection failed: {exc}; retrying in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            backoff = 1
            try:
                # Blocks; reconnects internally; returns after disconnect().
                client.loop_forever(retry_first_connection=True)
                return
            except KeyboardInterrupt:
                client.disconnect()
                self.stdout.write("Consumer stopped.")
                return

    @staticmethod
    def _request_stop(signum, frame):
        raise KeyboardInterrupt

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC_FILTER, qos=1)
            logger.info("Connected to broker; subscribed to %s", TOPIC_FILTER)
        else:
            logger.error("Broker connection refused: %s", reason_code)

    def _on_message(self, client, userdata, message):
        try:
            result = process_message(message.topic, message.payload)
        except Exception:  # noqa: BLE001 - one bad message must not kill the loop.
            logger.exception("Unexpected error processing %s", message.topic)
            return
        status = result["status"]
        if status == "stored":
            logger.info("Stored telemetry for vehicle %s", result.get("vehicle_id", "?"))
        elif status == "duplicate":
            logger.info("Duplicate telemetry ignored (%s)", result.get("record_id", "?"))
        else:
            logger.warning("Rejected telemetry: %s", result.get("reason", "?"))
        if self.run_once:
            client.disconnect()
