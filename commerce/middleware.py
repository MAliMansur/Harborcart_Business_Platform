import json
import logging
import time
import uuid
LOG = logging.getLogger("harborcart")
class RequestLogMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def process_exception(self, request, exception):
        from .services import BusinessError
        from django.shortcuts import render
        if isinstance(exception, BusinessError):
            return render(request, "commerce/error.html", {"title": "Request unavailable",
                "message": exception.message}, status=exception.status)

    def __call__(self, request):
        started = time.monotonic()
        request.request_id = uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        response["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response["Referrer-Policy"] = "same-origin"
        match = getattr(request, "resolver_match", None)
        route = (match.url_name or "unnamed") if match else "unmatched"
        LOG.info(json.dumps({"event":"request","request_id":request.request_id,
                            "route":route,"method":request.method[:10],
                            "status":response.status_code,
                            "duration_ms":round((time.monotonic()-started)*1000,2)}))
        return response
