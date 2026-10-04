from datetime import date, datetime, timedelta, timezone

import pytest

from dataset_requests.models import DatasetRequest
from episodes.models import Episode

pytestmark = pytest.mark.django_db

UTC = timezone.utc


def episode(code, robot, task, when, quality="good"):
    return Episode.objects.create(episode_id=code, robot_id=robot, task_name=task, recorded_at=when, duration_seconds=30, quality=quality)


def request(client, submitted, delivered_hours=None, status="submitted"):
    return DatasetRequest.objects.create(
        client=client, task_name="pick cup", episodes_requested=1, deadline=date(2030, 1, 1), status=status,
        submitted_at=submitted, delivered_at=submitted + timedelta(hours=delivered_hours) if delivered_hours else None,
    )


@pytest.fixture
def dataset(client_a):
    d1, d2 = datetime(2026, 8, 1, 10, tzinfo=UTC), datetime(2026, 8, 2, 10, tzinfo=UTC)
    outside = datetime(2026, 9, 1, 10, tzinfo=UTC)
    episode("E1", "arm-01", "pick cup", d1)
    episode("E2", "arm-01", "pick cup", d1)
    episode("E3", "arm-02", "pick cup", d1, quality="usable")
    episode("E4", "arm-01", "fold towel", d2)
    episode("E5", "arm-01", "fold towel", d2, quality="bad")
    episode("E6", "arm-01", "wipe table", datetime(2026, 8, 2, 23, 59, tzinfo=UTC))  # last minute of the range
    episode("E7", "arm-01", "pick cup", outside)
    for i, task in enumerate(["open drawer", "pour water", "stack blocks", "wipe table", "fold towel"]):
        episode(f"X{i}", "arm-03", task, d1)  # one extra good episode each -> 7 distinct tasks in range

    request(client_a, d1, delivered_hours=10, status="accepted")
    request(client_a, d1, delivered_hours=20, status="delivered")
    request(client_a, d2, delivered_hours=60, status="rejected")
    request(client_a, d2, status="in_progress")
    request(client_a, outside, delivered_hours=1, status="delivered")


def test_episodes_per_day_per_robot(operator_api, dataset):
    body = operator_api.get("/api/analytics?from=2026-08-01&to=2026-08-02").json()

    assert body["episodes_per_day_per_robot"] == [
        {"day": "2026-08-01", "robot_id": "arm-01", "episodes": 2},
        {"day": "2026-08-01", "robot_id": "arm-02", "episodes": 1},
        {"day": "2026-08-01", "robot_id": "arm-03", "episodes": 5},
        {"day": "2026-08-02", "robot_id": "arm-01", "episodes": 3},
    ]


def test_request_fulfilment_counts_and_median(operator_api, dataset):
    body = operator_api.get("/api/analytics?from=2026-08-01&to=2026-08-02").json()["requests"]

    assert body["by_status"] == {"submitted": 0, "in_progress": 1, "delivered": 1, "accepted": 1, "rejected": 1}
    assert body["delivered_count"] == 3
    assert body["median_submitted_to_delivered_seconds"] == 20 * 3600  # 10h, 20h, 60h -> 20h


def test_median_interpolates_for_even_counts_and_is_null_without_deliveries(operator_api, client_a):
    d = datetime(2026, 8, 1, tzinfo=UTC)
    assert operator_api.get("/api/analytics?from=2026-08-01&to=2026-08-01").json()["requests"]["median_submitted_to_delivered_seconds"] is None

    request(client_a, d, delivered_hours=10)
    request(client_a, d, delivered_hours=30)
    body = operator_api.get("/api/analytics?from=2026-08-01&to=2026-08-01").json()["requests"]
    assert body["median_submitted_to_delivered_seconds"] == 20 * 3600


def test_top_5_tasks_by_good_episodes_only(operator_api, dataset):
    body = operator_api.get("/api/analytics?from=2026-08-01&to=2026-08-02").json()["top_tasks_by_good_episodes"]

    assert len(body) == 5
    # Ties are broken alphabetically so the order is deterministic.
    assert body[0] == {"task_name": "fold towel", "good_episodes": 2}  # E5 (bad) excluded; X4 counts
    assert body[1] == {"task_name": "pick cup", "good_episodes": 2}    # E3 (usable) and E7 (out of range) excluded
    assert body[2] == {"task_name": "wipe table", "good_episodes": 2}
    assert [t["good_episodes"] for t in body[3:]] == [1, 1]


def test_range_validation_and_defaults(operator_api):
    assert operator_api.get("/api/analytics?from=2026-08-02&to=2026-08-01").status_code == 400
    assert operator_api.get("/api/analytics?from=nope").status_code == 400
    assert operator_api.get("/api/analytics?from=2020-01-01&to=2026-01-01").status_code == 400

    body = operator_api.get("/api/analytics").json()
    assert date.fromisoformat(body["to"]) - date.fromisoformat(body["from"]) == timedelta(days=30)


@pytest.mark.parametrize("role,expected", [("operator", 200), ("admin", 200), ("client", 403)])
def test_analytics_is_for_operators_and_admins(api_for, role, expected):
    assert api_for(role).get("/api/analytics").status_code == expected


def test_analytics_runs_a_fixed_number_of_queries_regardless_of_data_size(operator_api, dataset, django_assert_num_queries):
    # 1 session + 1 user lookup, then exactly 4 aggregate statements. No per-row Python work.
    with django_assert_num_queries(6):
        operator_api.get("/api/analytics?from=2026-08-01&to=2026-08-02")
