"""Analytics queries. Each one is a single SQL statement executed by PostgreSQL; nothing is aggregated in Python.

See README.md ("Analytics at scale") for how these behave with millions of episodes.
"""

from datetime import datetime, time, timedelta, timezone

from django.db.models import Aggregate, Count, DurationField, ExpressionWrapper, F
from django.db.models.functions import TruncDate

from dataset_requests.models import DatasetRequest
from episodes.models import Episode


class Median(Aggregate):
    """PostgreSQL's percentile_cont(0.5) ordered-set aggregate."""

    function = "PERCENTILE_CONT"
    name = "Median"
    template = "%(function)s(0.5) WITHIN GROUP (ORDER BY %(expressions)s)"
    allow_distinct = False


def date_range_bounds(start_date, end_date):
    """Inclusive calendar dates -> half-open UTC datetime interval [start, end)."""
    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start, end


def episodes_per_day_per_robot(start, end):
    return list(
        Episode.objects.filter(recorded_at__gte=start, recorded_at__lt=end)
        .annotate(day=TruncDate("recorded_at"))
        .values("day", "robot_id")
        .annotate(episodes=Count("id"))
        .order_by("day", "robot_id")
    )


def request_fulfilment(start, end):
    """Requests submitted in the range: count per status, and median submitted -> first delivery."""
    in_range = DatasetRequest.objects.filter(submitted_at__gte=start, submitted_at__lt=end)

    by_status = {status: 0 for status in DatasetRequest.Status.values}
    for row in in_range.values("status").annotate(count=Count("id")):
        by_status[row["status"]] = row["count"]

    delivered = in_range.filter(delivered_at__isnull=False)
    stats = delivered.aggregate(
        median=Median(ExpressionWrapper(F("delivered_at") - F("submitted_at"), output_field=DurationField())),
        delivered_count=Count("id"),
    )
    median = stats["median"]
    return {
        "by_status": by_status,
        "delivered_count": stats["delivered_count"],
        "median_submitted_to_delivered_seconds": median.total_seconds() if median is not None else None,
    }


def top_tasks_by_good_episodes(start, end, limit=5):
    return list(
        Episode.objects.filter(quality=Episode.Quality.GOOD, recorded_at__gte=start, recorded_at__lt=end)
        .values("task_name")
        .annotate(good_episodes=Count("id"))
        .order_by("-good_episodes", "task_name")[:limit]
    )
