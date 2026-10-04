import structlog
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = structlog.get_logger(__name__)


@require_GET
def health(request):
    """Liveness + DB check. Unauthenticated on purpose so load balancers / compose can call it."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.warning("health_db_unavailable", exc_info=True)
        return JsonResponse({"status": "degraded", "db": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "db": "ok"})
