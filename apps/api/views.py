from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def api_status(request):
    """API status endpoint."""
    return JsonResponse({
        'status': 'ok',
        'message': 'PCR Datenbank API is operational'
    })