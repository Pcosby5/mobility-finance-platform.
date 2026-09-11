"""Run the telemetry consumer as a free-tier *web* service.

Render's free plan has no background workers — only web services, which are
required to (a) listen on ``$PORT`` and (b) receive periodic HTTP traffic or
they spin down after 15 minutes. This command packages the existing consumer
for that environment:

1. The shared ``TelemetryConsumer`` (``telemetry/mqtt.py`` — the exact loop
   ``run_mqtt_consumer`` uses) runs in a daemon thread, ingesting
   ``vehicles/+/telemetry`` into the database. MQTT is outbound-only, so no
   inbound port is needed for the pipeline itself.
2. A minimal standard-library WSGI server binds ``0.0.0.0:$PORT`` and serves
   one endpoint, ``GET /healthz``: 200 with a small JSON status (MQTT state,
   counters, last message time) while the process is up. It intentionally
   shares nothing with the Django URLconf — no middleware, no auth surface,
   and no details beyond counters.

Keep-alive: a free web service that receives no traffic spins down and stops
consuming until the next ping. Ping ``/healthz`` at least every 14 minutes
from an external monitor (cron-job.org, UptimeRobot, ...) to keep it alive;
750 free instance-hours comfortably cover 24/7. A spin-down loses only the
messages published while stopped — QoS 1 redeliveries and the
``(device_id, recorded_at)`` unique constraint make re-ingestion harmless.

Local use (no env vars): binds 127.0.0.1:8080, so it is unreachable from
other machines but useful for inspecting ``/healthz`` while developing.
"""

import logging
import threading
import wsgiref.simple_server
from os import environ

from django.core.management.base import BaseCommand

from telemetry.mqtt import TelemetryConsumer

logger = logging.getLogger(__name__)


class QuietRequestHandler(wsgiref.simple_server.WSGIRequestHandler):
    """Send WSGI access lines to the logger instead of bare stderr, so Render's
    log stream (and local shells) show paho/ingest logs and probes together."""

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        logger.info("healthz: %s", format % args)


def build_app(consumer: TelemetryConsumer):
    """Return the one-endpoint WSGI app. Kept a function (not a closure at
    import time) so tests can construct isolated instances."""

    def app(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path != "/healthz":
            start_response("404 Not Found", [("Content-Type", "application/json")])
            yield b'{"error": "not found"}'
            return
        start_response("200 OK", [("Content-Type", "application/json")])
        import json

        yield json.dumps(consumer.status).encode()

    return app


class Command(BaseCommand):
    help = (
        "Run the MQTT telemetry consumer with an HTTP /healthz endpoint so it "
        "can deploy as a free-tier Render web service."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            type=int,
            default=int(environ.get("PORT", "8080")),
            help="HTTP port for /healthz (default: $PORT or 8080).",
        )
        parser.add_argument(
            "--host",
            default=None,
            help="Bind address (default: 0.0.0.0 if $PORT is set, else 127.0.0.1).",
        )

    def handle(self, *args, **options):
        host = options["host"] or ("0.0.0.0" if "PORT" in environ else "127.0.0.1")
        port = options["port"]

        consumer = TelemetryConsumer()
        thread = threading.Thread(target=consumer.run, name="mqtt-consumer", daemon=True)
        thread.start()

        server = wsgiref.simple_server.make_server(
            host, port, build_app(consumer), handler_class=QuietRequestHandler
        )
        self.stdout.write(f"Telemetry gateway listening on {host}:{port} (/healthz)")
        try:
            # serve_forever polls every 0.5s; a plain EINTR/shutdown race is
            # retried rather than crashing the service.
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        except OSError as exc:
            logger.error("Health server error: %s", exc)
        finally:
            server.server_close()
            consumer.stop()
            thread.join(timeout=5)
            self.stdout.write("Telemetry gateway stopped.")
