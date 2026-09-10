"""Payment use cases: initialization, verification and idempotent settlement.

Settlement rules (the financially sensitive part):

* Webhook payloads only *point at* a transaction; the handler always re-verifies
  with the provider before money moves. A forged or spurious payload can never
  change a balance by itself.
* Terminal transitions use conditional ``UPDATE ... WHERE status = 'PENDING'``
  statements, so under concurrent redelivery exactly one request wins and the
  loser observes "already processed" instead of double-crediting.
* The payment status update and the loan balance reduction share one database
  transaction guarded by a loan row lock, so a crash cannot mark a payment
  successful without applying it (or vice versa).
"""

import json
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from loans.models import Loan
from rest_framework.exceptions import PermissionDenied, ValidationError
from users.models import User

from .models import Payment, WebhookEvent
from .providers import PaymentProviderError, generate_reference, get_provider


@transaction.atomic
def initialize_payment(*, actor, loan_id, provider_name, amount=None):
    """Create a PENDING payment and start the transaction at the provider."""
    loan = (
        Loan.objects.select_for_update()
        .select_related("customer", "customer__user")
        .get(pk=loan_id)
    )
    if loan.status != Loan.Status.ACTIVE:
        raise ValidationError({"loan": "Only ACTIVE loans can receive payments."})
    # Customers pay their own loans; staff may initialize on any loan. Object
    # ownership is enforced here so the view can stay permission-thin.
    if actor.role not in (User.Role.OPERATIONS, User.Role.ADMIN):
        if loan.customer.user_id != actor.pk:
            raise PermissionDenied("You can only start payments for your own loans.")
    amount = amount if amount is not None else loan.outstanding_balance
    if amount <= 0 or amount > loan.outstanding_balance:
        raise ValidationError(
            {
                "amount": (
                    f"Amount must be between 0.01 and the outstanding balance "
                    f"of {loan.outstanding_balance}."
                )
            }
        )
    try:
        provider = get_provider(provider_name)
    except PaymentProviderError as exc:
        raise ValidationError({"provider": str(exc)}) from exc
    reference = generate_reference(prefix="PSK" if provider.name == "PAYSTACK" else "MOMO")
    payment = Payment.objects.create(
        loan=loan,
        customer=loan.customer,
        provider=provider.name,
        reference=reference,
        currency=loan.currency,
        amount=amount,
    )
    user = loan.customer.user
    metadata = {
        "loan_id": str(loan.pk),
        "customer_id": str(loan.customer_id),
        # Paystack requires an email; profiles may not carry one in the demo.
        "email": user.email or f"{user.username}@example.com",
    }
    # Send the payer back into the app after Paystack's hosted checkout. The
    # webhook (or a manual verify) remains the settlement path; the redirect
    # is only a UX convenience.
    base_url = (settings.PUBLIC_SITE_BASE_URL or "").rstrip("/")
    callback_url = f"{base_url}/payments?reference={reference}" if base_url else None
    # A provider outage is a handled client error, not a 500: the payment row
    # created above rolls back with the transaction, so no orphan PENDING rows.
    try:
        result = provider.create_payment(
            reference=reference,
            amount=amount,
            currency=loan.currency,
            metadata=metadata,
            callback_url=callback_url,
        )
    except PaymentProviderError as exc:
        raise ValidationError(
            {"detail": "Payment provider is unavailable; try again."}
        ) from exc
    payment.raw_event = {"initialization": result}
    payment.save(update_fields=["raw_event", "updated_at"])
    return payment, result


def _apply_success(payment, verified):
    """Mark a PENDING payment SUCCESS and reduce the loan balance atomically."""
    mismatch = None
    if verified.get("amount") is not None and Decimal(verified["amount"]) != payment.amount:
        mismatch = "Verified amount does not match the payment record."
    elif verified.get("currency") is not None and verified["currency"] != payment.currency:
        mismatch = "Verified currency does not match the payment record."
    with transaction.atomic():
        loan = Loan.objects.select_for_update().get(pk=payment.loan_id)
        if mismatch is None and payment.amount > loan.outstanding_balance:
            mismatch = "Amount exceeds the outstanding balance."
        if mismatch:
            updated = Payment.objects.filter(pk=payment.pk, status=Payment.Status.PENDING).update(
                status=Payment.Status.FAILED,
                failure_reason=mismatch,
                raw_event={**payment.raw_event, "verification": verified["raw"]},
                updated_at=timezone.now(),
            )
            return "processed" if updated else "already processed"
        updated = Payment.objects.filter(pk=payment.pk, status=Payment.Status.PENDING).update(
            status=Payment.Status.SUCCESS,
            provider_transaction_id=verified["provider_transaction_id"],
            raw_event={**payment.raw_event, "verification": verified["raw"]},
            updated_at=timezone.now(),
        )
        if not updated:
            # A concurrent delivery already settled this payment.
            return "already processed"
        loan.outstanding_balance = loan.outstanding_balance - payment.amount
        if loan.outstanding_balance == 0:
            loan.status = Loan.Status.COMPLETED
        loan.save(update_fields=["outstanding_balance", "status", "updated_at"])
        return "processed"


def _apply_failure(payment, reason):
    """Mark a PENDING payment FAILED; balances are untouched."""
    with transaction.atomic():
        updated = Payment.objects.filter(pk=payment.pk, status=Payment.Status.PENDING).update(
            status=Payment.Status.FAILED,
            failure_reason=reason[:255],
            updated_at=timezone.now(),
        )
    return "processed" if updated else "already processed"


def refresh_payment_status(payment):
    """Re-verify a payment with its provider and apply the outcome.

    Used by the verify endpoint; also gives integrations a pull-based fallback
    when webhooks are delayed or unavailable.
    """
    if payment.status != Payment.Status.PENDING:
        return payment, f"Payment is already {payment.status}."
    provider = get_provider(payment.provider)
    try:
        verified = provider.verify_payment(payment.reference)
    except PaymentProviderError as exc:
        raise ValidationError({"detail": "Payment provider is unavailable; try again."}) from exc
    if verified["status"] == "success":
        note = _apply_success(payment, verified)
    elif verified["status"] == "failed":
        note = _apply_failure(payment, "Provider reported the payment failed.")
    else:
        note = "Provider reports the payment is still pending."
    payment.refresh_from_db()
    return payment, note


def _record_event(provider_name, event_type, signature, payload, reference, status, note):
    return WebhookEvent.objects.create(
        provider=provider_name,
        event_type=event_type[:50],
        signature=(signature or "")[:255],
        payload=payload if payload is not None else {},
        delivery_reference=reference or "",
        status=status,
        note=note[:255],
        processed_at=timezone.now() if status != WebhookEvent.Status.RECEIVED else None,
    )


def handle_webhook(*, provider_name, body, signature):
    """Process one raw webhook delivery. Returns a dict for the view to map to HTTP.

    Only the reference is taken from the payload; the outcome is always fetched
    from the provider itself. Duplicate deliveries of an already-terminal
    payment are recorded and ignored without any financial side effect.
    """
    provider = get_provider(provider_name)
    if not provider.verify_webhook_signature(body, signature):
        _record_event(
            provider_name,
            "unknown",
            signature,
            None,
            "",
            WebhookEvent.Status.IGNORED,
            "invalid signature",
        )
        return {"signature_valid": False}
    try:
        event = json.loads(body.decode("utf-8"))
        if not isinstance(event, dict):
            raise ValueError("payload is not an object")
    except (UnicodeDecodeError, ValueError):
        _record_event(
            provider_name,
            "unknown",
            signature,
            None,
            "",
            WebhookEvent.Status.IGNORED,
            "invalid json body",
        )
        return {"signature_valid": True, "outcome": "ignored", "note": "invalid json body"}
    event_type = str(event.get("event", "unknown"))
    reference = str((event.get("data") or {}).get("reference") or "")
    webhook_event = WebhookEvent.objects.create(
        provider=provider_name,
        event_type=event_type[:50],
        signature=(signature or "")[:255],
        payload=event,
        delivery_reference=reference,
    )
    if not reference:
        return _finalize(webhook_event, WebhookEvent.Status.IGNORED, "missing reference")
    payment = Payment.objects.filter(reference=reference).first()
    if payment is None:
        return _finalize(webhook_event, WebhookEvent.Status.IGNORED, "unknown reference")
    if payment.status != Payment.Status.PENDING:
        return _finalize(
            webhook_event,
            WebhookEvent.Status.IGNORED,
            f"duplicate delivery; payment already {payment.status}",
        )
    try:
        verified = provider.verify_payment(reference)
    except PaymentProviderError:
        webhook_event.note = "provider verification unavailable; delivery should retry"
        webhook_event.save(update_fields=["note"])
        return {"signature_valid": True, "outcome": "retry", "note": webhook_event.note}
    if verified["status"] == "success":
        note = _apply_success(payment, verified)
    elif verified["status"] == "failed":
        note = _apply_failure(payment, "Provider reported the payment failed.")
    else:
        webhook_event.note = "payment still pending at the provider"
        webhook_event.save(update_fields=["note"])
        return {"signature_valid": True, "outcome": "pending", "note": webhook_event.note}
    status = WebhookEvent.Status.PROCESSED if note == "processed" else WebhookEvent.Status.IGNORED
    return _finalize(webhook_event, status, note)


def _finalize(webhook_event, status, note):
    webhook_event.status = status
    webhook_event.note = note[:255]
    webhook_event.processed_at = timezone.now()
    webhook_event.save(update_fields=["status", "note", "processed_at"])
    return {"signature_valid": True, "outcome": status.lower(), "note": note}
