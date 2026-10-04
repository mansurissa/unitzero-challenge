import time

import structlog

logger = structlog.get_logger("request")


class RequestLogMiddleware:
    """Emits exactly one structured log line per HTTP request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        # request.user is set by AuthenticationMiddleware further down the stack.
        user = getattr(request, "user", None)
        user_id = user.pk if user is not None and user.is_authenticated else None

        if response.status_code >= 500:
            log = logger.error
        elif response.status_code >= 400:
            log = logger.warning
        else:
            log = logger.info
        log(
            "request",
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=user_id,
        )
        return response
