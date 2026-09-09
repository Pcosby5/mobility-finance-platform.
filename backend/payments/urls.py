from django.urls import path

from .views import (
    MockMomoWebhookView,
    PaymentInitializeView,
    PaymentListView,
    PaymentVerifyView,
    PaystackWebhookView,
    WebhookEventListView,
)

app_name = "payments"
urlpatterns = [
    path("payments/", PaymentListView.as_view(), name="list"),
    path("payments/initialize/", PaymentInitializeView.as_view(), name="initialize"),
    path("payments/<str:reference>/verify/", PaymentVerifyView.as_view(), name="verify"),
    path("payments/webhook-events/", WebhookEventListView.as_view(), name="webhook-events"),
    path("webhooks/paystack/", PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("webhooks/momo/simulate/", MockMomoWebhookView.as_view(), name="momo-simulate"),
]
