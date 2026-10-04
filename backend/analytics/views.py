from datetime import date, timedelta

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import IsOperatorOrAdmin

from . import queries

DEFAULT_SPAN_DAYS = 30
MAX_SPAN_DAYS = 3 * 366


def parse_range(params):
    """`from` / `to` as inclusive ISO dates. Defaults: the last 30 days."""
    try:
        end = date.fromisoformat(params["to"]) if params.get("to") else timezone.localdate()
        start = date.fromisoformat(params["from"]) if params.get("from") else end - timedelta(days=DEFAULT_SPAN_DAYS)
    except ValueError:
        raise ValidationError({"detail": "'from' and 'to' must be dates formatted YYYY-MM-DD."}) from None
    if start > end:
        raise ValidationError({"detail": "'from' must not be after 'to'."})
    if (end - start).days > MAX_SPAN_DAYS:
        raise ValidationError({"detail": f"Range too large (max {MAX_SPAN_DAYS} days)."})
    return start, end


@api_view(["GET"])
@permission_classes([IsOperatorOrAdmin])
def analytics(request):
    start_date, end_date = parse_range(request.query_params)
    start, end = queries.date_range_bounds(start_date, end_date)

    return Response({
        "from": start_date,
        "to": end_date,
        "episodes_per_day_per_robot": queries.episodes_per_day_per_robot(start, end),
        "requests": queries.request_fulfilment(start, end),
        "top_tasks_by_good_episodes": queries.top_tasks_by_good_episodes(start, end),
    })
