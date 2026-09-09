from django.urls import path

from .views import CreditAssessmentDetailView

app_name = "credit"
urlpatterns = [path("<uuid:pk>/", CreditAssessmentDetailView.as_view(), name="detail")]
