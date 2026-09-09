from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """Liveness only; database readiness is checked separately during setup."""
    return JsonResponse({"status": "ok"})
