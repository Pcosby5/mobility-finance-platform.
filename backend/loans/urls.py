from django.urls import path

from .views import (
    LoanActivateView,
    LoanCancelView,
    LoanDetailView,
    LoanListCreateView,
    LoanScheduleView,
)

app_name = "loans"
urlpatterns = [
    path("", LoanListCreateView.as_view(), name="list"),
    path("<uuid:pk>/", LoanDetailView.as_view(), name="detail"),
    path("<uuid:pk>/installments/", LoanScheduleView.as_view(), name="installments"),
    path("<uuid:pk>/activate/", LoanActivateView.as_view(), name="activate"),
    path("<uuid:pk>/cancel/", LoanCancelView.as_view(), name="cancel"),
]
