"""Tests for the shared MQTT consumer and the free-tier gateway command.

The consumer's ingest logic is covered by ProcessMessageTests (services.py);
these tests cover the transport wrapper: counters, stop semantics, reconnect
loop shape, the ``--once`` delegation of the standalone command, and the
gateway's /healthz endpoint — the observability surface for hosts without
shell access (Render's free tier has no SSH).
"""

import json
import threading
import urllib.request
import wsgiref.simple_server
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import TelemetryRecord
from .mqtt import TelemetryConsumer
from .tests import TelemetryFixtureMixin

TOPIC = "vehicles/1/telemetry"


def make_delivery(payload) -> mock.Mock:
    message = mock.Mock()
    message.topic = TOPIC
    message.payload = json.dumps(payload).encode() if isinstance(payload, dict) else payload
    return message


def valid_payload(**overrides):
    payload = {
        "device_id": "GPS-001",
        "latitude": 5.6037,
        "longitude": -0.1870,
        "speed": 41.0,
        "recorded_at": (timezone.now() - timedelta(seconds=5)).isoformat(),
    }
    payload.update(overrides)
    return payload


class TelemetryConsumerTests(TelemetryFixtureMixin, TestCase):
    def consume(self, consumer, payload):
        consumer._on_message(mock.Mock(), None, make_delivery(payload))

    def test_stored_message_updates_counters_and_database(self):
        consumer = TelemetryConsumer()
        self.consume(consumer, valid_payload())
        self.assertEqual(consumer.status["stored"], 1)
        self.assertEqual(TelemetryRecord.objects.count(), 1)
        self.assertIsNotNone(consumer.status["last_message_at"])

    def test_rejections_are_counted_without_raising(self):
        consumer = TelemetryConsumer()
        self.consume(consumer, valid_payload(device_id="GPS-404"))
        self.consume(consumer, b"{not json")
        self.assertEqual(consumer.status["rejected"], 2)
        self.assertEqual(consumer.status["stored"], 0)
        self.assertEqual(TelemetryRecord.objects.count(), 0)

    def test_duplicates_counted_separately(self):
        consumer = TelemetryConsumer()
        payload = valid_payload()  # one fixed recorded_at -> a true duplicate
        self.consume(consumer, payload)
        self.consume(consumer, payload)
        self.assertEqual(consumer.status["stored"], 1)
        self.assertEqual(consumer.status["duplicates"], 1)

    def test_unexpected_pipeline_error_is_counted_not_raised(self):
        consumer = TelemetryConsumer()
        with mock.patch("telemetry.mqtt.process_message", side_effect=RuntimeError("db down")):
            self.consume(consumer, valid_payload())  # must not raise
        self.assertEqual(consumer.status["errors"], 1)
        self.assertEqual(consumer.status["stored"], 0)

    def test_stop_after_disconnects_client(self):
        consumer = TelemetryConsumer(stop_after=1)
        client = mock.Mock()
        consumer._client = client  # run() wires this before deliveries arrive
        consumer._on_message(client, None, make_delivery(valid_payload()))
        client.disconnect.assert_called_once()

    def test_stop_is_safe_before_any_connection(self):
        consumer = TelemetryConsumer()
        consumer.stop()  # must not raise
        self.assertEqual(consumer.status["state"], "starting")

    def test_initial_status_advertises_configuration(self):
        status = TelemetryConsumer().status
        self.assertEqual(status["state"], "starting")
        self.assertEqual(status["topic"], "vehicles/+/telemetry")
        self.assertEqual(status["stored"], 0)
        self.assertIn("broker", status)


class ConsumerLoopTests(TelemetryFixtureMixin, TestCase):
    """Drive run() with a mocked paho client to pin the reconnect contract."""

    def run_with_client(self, consumer, client):
        with mock.patch("telemetry.mqtt.mqtt.Client", return_value=client):
            consumer.run()

    def test_run_subscribes_and_cleanly_stops(self):
        consumer = TelemetryConsumer()
        client = mock.MagicMock()

        def loop_forever(retry_first_connection):
            consumer._on_connect(client, None, None, 0, None)
            consumer.stop()  # supervisor or another thread asks to stop
            return 0

        client.loop_forever.side_effect = loop_forever
        self.run_with_client(consumer, client)
        client.connect.assert_called_once()
        client.subscribe.assert_called_once_with("vehicles/+/telemetry", qos=1)
        self.assertEqual(consumer.status["state"], "stopped")

    def test_run_retries_failed_connects_until_stopped(self):
        consumer = TelemetryConsumer()
        client = mock.MagicMock()
        client.connect.side_effect = OSError("connection refused")
        # The first retry wait is 1s; stop well inside it so the test is fast.
        timer = threading.Timer(0.1, consumer.stop)
        timer.start()
        try:
            self.run_with_client(consumer, client)
        finally:
            timer.cancel()
        self.assertGreaterEqual(client.connect.call_count, 1)
        self.assertEqual(consumer.status["state"], "stopped")

    def test_refused_connection_reason_does_not_subscribe(self):
        consumer = TelemetryConsumer()
        client = mock.MagicMock()
        client.loop_forever.side_effect = lambda retry_first_connection: (
            consumer._on_connect(client, None, None, "not authorized", None),
            consumer.stop(),
        )
        self.run_with_client(consumer, client)
        client.subscribe.assert_not_called()


class RunMqttConsumerCommandTests(TelemetryFixtureMixin, TestCase):
    def test_delegates_to_shared_consumer(self):
        with mock.patch(
            "telemetry.management.commands.run_mqtt_consumer.TelemetryConsumer"
        ) as factory:
            call_command("run_mqtt_consumer")
        factory.assert_called_once_with(stop_after=0)
        factory.return_value.run.assert_called_once_with()

    def test_once_flag_limits_to_a_single_message(self):
        with mock.patch(
            "telemetry.management.commands.run_mqtt_consumer.TelemetryConsumer"
        ) as factory:
            call_command("run_mqtt_consumer", "--once")
        factory.assert_called_once_with(stop_after=1)


class GatewayHealthAppTests(SimpleTestCase):
    def collect(self, path):
        app = __import__(
            "telemetry.management.commands.run_telemetry_gateway",
            fromlist=["build_app"],
        ).build_app(TelemetryConsumer())
        status_box = []

        def start_response(status, headers):
            status_box.append(status)

        environ = {"PATH_INFO": path, "REQUEST_METHOD": "GET"}
        chunks = list(app(environ, start_response))
        return status_box[0], b"".join(chunks)

    def test_healthz_reports_consumer_status(self):
        status, body = self.collect("/healthz")
        self.assertEqual(status, "200 OK")
        data = json.loads(body)
        self.assertEqual(data["state"], "starting")
        self.assertEqual(data["topic"], "vehicles/+/telemetry")

    def test_unknown_path_returns_404(self):
        status, _ = self.collect("/nope")
        self.assertEqual(status, "404 Not Found")


class GatewayServerTests(SimpleTestCase):
    """End-to-end: a real socket serving /healthz from the running app."""

    def test_healthz_served_over_real_socket(self):
        from telemetry.management.commands.run_telemetry_gateway import build_app

        consumer = TelemetryConsumer()
        server = wsgiref.simple_server.make_server("127.0.0.1", 0, build_app(consumer))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/healthz", timeout=5
            ) as response:
                body = json.load(response)
            self.assertEqual(response.status, 200)
            self.assertEqual(body["state"], "starting")
            self.assertEqual(body["broker"], consumer.status["broker"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
