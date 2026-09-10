"""Payment provider abstraction.

The rest of the system depends on the small ``PaymentProvider`` interface, never
on Paystack or any vendor SDK directly:

* ``create_payment(reference, amount, currency, metadata) -> dict`` — start a
  transaction at the provider and return its data (e.g. a checkout URL).
* ``verify_payment(reference) -> dict`` — fetch the provider's own record of the
  transaction. Webhook payloads are never trusted on their own; the handler
  always re-verifies against the provider before moving money. Implementations
  return ``{"status": "success"|"failed"|"pending", "provider_transaction_id":
  str|None, "amount": str, "currency": str, "raw": dict}``.
* ``verify_webhook_signature(body, signature) -> bool`` — provider-specific
  authenticity check for the raw request body.

Secrets come from environment variables only and are never logged. Adding a
future provider means implementing this interface and registering it in
``get_provider`` — no changes to services, views or webhooks.
"""

import hashlib
import hmac
import secrets
import threading
from decimal import Decimal

import requests
from django.conf import settings

PAYSTACK_API_BASE = "https://api.paystack.co"


class PaymentProviderError(Exception):
    """Raised when a provider interaction fails; never exposes credentials."""


class PaymentProvider:
    name = ""

    def create_payment(  # pragma: no cover
        self, reference, amount, currency, metadata, callback_url=None
    ):
        raise NotImplementedError

    def verify_payment(self, reference):  # pragma: no cover
        raise NotImplementedError

    def verify_webhook_signature(self, body, signature):  # pragma: no cover
        raise NotImplementedError


class PaystackProvider(PaymentProvider):
    """Paystack TEST-mode client over the plain REST API.

    Amounts are transmitted in the provider's required subunit (pesewas/kobo);
    the database keeps major units so the ledger stays human-readable.
    """

    name = "PAYSTACK"

    def __init__(self, secret_key=None):
        self.secret_key = secret_key or settings.PAYSTACK_SECRET_KEY
        if not self.secret_key:
            raise PaymentProviderError("PAYSTACK_SECRET_KEY is not configured.")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def create_payment(self, reference, amount, currency, metadata, callback_url=None):
        subunit = Decimal("100")
        payload = {
            "reference": reference,
            "amount": int((Decimal(amount) * subunit).quantize(Decimal("1"))),
            "email": metadata.get("email"),
            "currency": currency,
            "metadata": {key: value for key, value in metadata.items() if key != "email"},
        }
        if callback_url:
            # Hosted-checkout redirect target; settlement still arrives via the
            # webhook or a pull-based verify, never through this redirect.
            payload["callback_url"] = callback_url
        try:
            response = requests.post(
                f"{PAYSTACK_API_BASE}/transaction/initialize",
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise PaymentProviderError("Payment provider is unavailable.") from exc
        if not body.get("status"):
            raise PaymentProviderError("Payment provider rejected the transaction.")
        data = body.get("data", {})
        # Normalize for the app: Paystack names its checkout link
        # "authorization_url"; expose it as checkout_url so the view and web
        # client stay provider-agnostic.
        if data.get("authorization_url") and not data.get("checkout_url"):
            data["checkout_url"] = data["authorization_url"]
        return data

    def verify_payment(self, reference):
        try:
            response = requests.get(
                f"{PAYSTACK_API_BASE}/transaction/verify/{reference}",
                headers=self._headers(),
                timeout=15,
            )
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise PaymentProviderError("Payment provider is unavailable.") from exc
        if not body.get("status"):
            raise PaymentProviderError("Payment verification failed at the provider.")
        data = body.get("data", {})
        return {
            "status": data.get("status", "pending"),
            "provider_transaction_id": str(data.get("id") or "") or None,
            "amount": str(Decimal(data.get("amount", 0)) / 100),
            "currency": data.get("currency"),
            "raw": data,
        }

    def verify_webhook_signature(self, body, signature):
        # Paystack signs the raw bytes with HMAC-SHA512 of the secret key.
        if not signature or not self.secret_key:
            return False
        digest = hmac.new(self.secret_key.encode(), body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(digest, signature)


class MockMomoProvider(PaymentProvider):
    """Simulated mobile-money provider for the demo.

    No network calls. The simulated lifecycle is PENDING -> SUCCESS/FAILED and
    webhook callbacks are triggered explicitly by a development-only endpoint,
    which also lets a tester fire duplicate or delayed deliveries on demand.
    """

    name = "MOCK_MOMO"

    # Simulated provider-side state is shared across instances: get_provider
    # builds a fresh object per call, mirroring an external service that keeps
    # its own transaction state. Demo only; never used in production.
    _transactions = {}
    _lock = threading.Lock()

    def create_payment(self, reference, amount, currency, metadata, callback_url=None):
        with self._lock:
            self._transactions[reference] = {"status": "pending", "attempts": 0}
        return {
            "checkout_url": None,
            "provider_transaction_id": None,
            "message": "Simulated MoMo charge created; trigger the callback to resolve it.",
        }

    def verify_payment(self, reference):
        with self._lock:
            record = self._transactions.get(reference)
            if record is not None:
                record["attempts"] += 1
        status = record["status"] if record else "failed"
        return {
            "status": status,
            "provider_transaction_id": f"MOCK-{reference[:12]}" if record else None,
            "amount": None,
            "currency": None,
            "raw": dict(record) if record else {},
        }

    def resolve(self, reference, status):
        """Development helper: resolve a simulated charge as success or failed."""
        with self._lock:
            record = self._transactions.get(reference)
            if record is None:
                raise PaymentProviderError("Unknown simulated transaction.")
            record["status"] = status

    def verify_webhook_signature(self, body, signature):
        # The simulator is local-only; authenticity comes from the dev guard,
        # but a shared dev secret keeps the flow identical to a real provider.
        expected = hmac.new(
            settings.MOCK_MOMO_WEBHOOK_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")


_PROVIDERS = {
    PaystackProvider.name: PaystackProvider,
    MockMomoProvider.name: MockMomoProvider,
}


def get_provider(name):
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise PaymentProviderError(f"Unknown payment provider: {name}") from None


def generate_reference(prefix="PAY"):
    return f"{prefix}-{secrets.token_hex(10).upper()}"
