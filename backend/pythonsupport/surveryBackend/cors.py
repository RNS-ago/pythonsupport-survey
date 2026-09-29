from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers


def cors_middleware(get_response):
    """Let the frontend call the API, cookies included, when it lives on another origin.

    Sits above CsrfViewMiddleware so its 403s carry the headers too; without
    them the browser hides the status and the frontend sees a network error.
    """
    def middleware(request):
        origin = request.headers.get('Origin')
        allowed = origin in settings.FRONTEND_ORIGINS
        # Answer preflights here so require_POST never sees them.
        if allowed and request.method == 'OPTIONS':
            response = HttpResponse()
        else:
            response = get_response(request)
        if allowed:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken'
        patch_vary_headers(response, ['Origin'])
        return response
    return middleware
