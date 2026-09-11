"""Shared MQTT consumer for vehicle telemetry.

The consumer is transport glue around ``telemetry.services.process_message``:
it connects to the configured broker, subscribes to ``vehicles/+/telemetry``
at QoS 1, and feeds every delivery into the ingest pipeline. Keeping it here
lets two entry points share one implementation — the standalone
``run_mqtt_consumer`` command (local dev, paid-plan worker) and the free-tier
``run_telemetry_gateway`` command (consumer thread + health HTTP server).

Error policy is unchanged from the original command: malformed or
unknown-device messages are logged and discarded (device faults, not
transport faults); broker errors use bounded exponential backoff on the
initial connect and paho's internal reconnect with resubscribe afterwards;
SIGTERM/SIGINT shut down cleanly.
"""

import logging
import threading

import paho.mqtt.client as mqtt
from django.conf import settings

from telemetry.services import process_message

logger = logging.getLogger(__name__)

TOPIC_FILTER = "vehicles/+/telemetry"
CONNECT_BACKOFF_MIN_S = 1
CONNECT_BACKOFF_MAX_S = 30
KEEPALIVE_SECONDS = 60


class TelemetryConsumer:
    """Own one paho client: connect, subscribe, ingest, reconnect.

    ``run()`` blocks until ``stop()`` is called from another thread (or the
    process receives SIGINT/SIGTERM). The ``status`` dict is a tiny health
    surface the gateway's HTTP server exposes at ``/healthz`` so an operator
    can tell a subscribed consumer from a crashed one without shell access —
    the thing Render's free tier does not offer.
    """

    def __init__(self, stop_after: int = 0):
        """``stop_after`` > 0 disconnects after that many deliveries (the
        standalone command's ``--once`` debugging flag); 0 runs until
        ``stop()`` or the process is signalled."""
        self._stop_after = max(0, stop_after)
        self._processed = 0
        self.status = {
            "state": "starting",  # starting | connecting | connected | stopped
            "broker": settings.MQTT_BROKER_HOST,
            "port": settings.MQTT_BROKER_PORT,
            "topic": TOPIC_FILTER,
            "stored": 0,
            "duplicates": 0,
            "rejected": 0,
            "errors": 0,
            "last_message_at": None,  # ISO timestamp of the last delivery.
        }
        self._stop_event = threading.Event()
        self._client: mqtt.Client | None = None

    # -- control -----------------------------------------------------------

    def stop(self):
        """Ask the loop to exit; safe to call from any thread."""
        self._stop_event.set()
        client = self._client
        if client is not None:
            # paho disconnects on the network thread; loop_forever() then
            # returns and run() observes the stop event.
            client.disconnect()

    # -- loop --------------------------------------------------------------

    def run(self):
        logger.info(
            "Telemetry consumer starting: broker %s:%s",
            settings.MQTT_BROKER_HOST,
            settings.MQTT_BROKER_PORT,
        )
        self.status["state"] = "connecting"
        backoff = CONNECT_BACKOFF_MIN_S
        while not self._stop_event.is_set():
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="telemetry-consumer")
            self._client = client
            if settings.MQTT_USERNAME:
                client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD or None)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.reconnect_delay_set(min_delay=1, max_delay=30)

            try:
                client.connect(
                    settings.MQTT_BROKER_HOST,
                    settings.MQTT_BROKER_PORT,
                    KEEPALIVE_SECONDS,
                )
            except OSError as exc:
                logger.warning("Broker connection failed: %s; retrying in %ss", exc, backoff)
                self.status["state"] = "connecting"
                if self._stop_event.wait(timeout=backoff):
                    break
                backoff = min(backoff * 2, CONNECT_BACKOFF_MAX_S)
                continue
            backoff = CONNECT_BACKOFF_MIN_S
            try:
                # Blocks until disconnect(); reconnects internally and paho
                # resubscribes (subscriptions are part of session state kept
                # by loop_forever's reconnect handling).
                client.loop_forever(retry_first_connection=True)
            except OSError as exc:
                logger.warning("Broker loop error: %s; reconnecting", exc)
                continue
            if self._stop_event.is_set():
                break
            # loop_forever returned without a stop request (broker dropped us
            # without an exception) — reconnect from the top.
            self.status["state"] = "connecting"
            logger.info("Reconnecting to broker")
        self.status["state"] = "stopped"
        logger.info("Telemetry consumer stopped")

    # -- callbacks ----------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC_FILTER, qos=1)
            self.status["state"] = "connected"
            logger.info("Connected to broker; subscribed to %s", TOPIC_FILTER)
        else:
            logger.error("Broker connection refused: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.status["state"] = "connecting"
        logger.warning("Broker disconnected (reason %s); will reconnect", reason_code)

    def _on_message(self, client, userdata, message):
        from django.utils import timezone

        try:
            result = process_message(message.topic, message.payload)
        except Exception:  # noqa: BLE001 - one bad message must not kill the loop.
            self.status["errors"] += 1
            self.status["last_message_at"] = timezone.now().isoformat()
            logger.exception("Unexpected error processing %s", message.topic)
            return
        self.status["last_message_at"] = timezone.now().isoformat()
        self._processed += 1
        if self._stop_after and self._processed >= self._stop_after:
            logger.info("Processed %s message(s); stopping as requested", self._processed)
            self.stop()
        status = result["status"]
        if status == "stored":
            self.status["stored"] += 1
            logger.info("Stored telemetry for vehicle %s", result.get("vehicle_id", "?"))
        elif status == "duplicate":
            self.status["duplicates"] += 1
            logger.info("Duplicate telemetry ignored (%s)", result.get("record_id", "?"))
        else:
            self.status["rejected"] += 1
            logger.warning("Rejected telemetry: %s", result.get("reason", "?"))
