"""Run the MQTT telemetry consumer as a long-lived process.

Why a separate process: the broker connection is stateful and long-lived, so it
must never live inside Django's request/response workers — a broker outage or a
slow message burst must not affect HTTP latency, and a web redeploy must not
drop the subscription. Locally this is simply ``python manage.py
run_mqtt_consumer`` next to ``runserver``; the container entrypoint runs it as
its own Compose service, and on Render's paid plans it is a background worker.

On Render's **free** tier, background workers don't exist — use
``run_telemetry_gateway`` instead, which runs this same consumer (via the
shared ``TelemetryConsumer`` in ``telemetry/mqtt.py``) behind a minimal HTTP
health endpoint so it can deploy as a free web service.

Error policy (in the shared class): malformed or unknown-device messages are
logged and discarded (they are device faults, not transport faults). Broker
errors use bounded exponential backoff on the initial connect, and paho's
internal reconnect with resubscribe afterwards. Ctrl+C / SIGTERM shut down
cleanly.
"""

import signal

from django.core.management.base import BaseCommand

from telemetry.mqtt import TelemetryConsumer


class Command(BaseCommand):
    help = "Consume vehicle telemetry from the MQTT broker."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Exit after processing the first message.",
        )

    def handle(self, *args, **options):
        # SIGTERM should behave like Ctrl+C so supervisors stop us cleanly.
        signal.signal(signal.SIGTERM, self._request_stop)
        consumer = TelemetryConsumer(stop_after=1 if options["once"] else 0)
        try:
            consumer.run()
        except KeyboardInterrupt:
            consumer.stop()
            self.stdout.write("Consumer stopped.")

    @staticmethod
    def _request_stop(signum, frame):
        raise KeyboardInterrupt
