"""Assignment rules: quality, one request at a time, only while in progress, and the delivery guard."""

from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction

from core.exceptions import Conflict, DomainError
from dataset_requests import services
from dataset_requests.models import Assignment, DatasetRequest
from episodes.models import Episode

pytestmark = pytest.mark.django_db

S = DatasetRequest.Status
TOMORROW = date.today() + timedelta(days=1)


def make_episode(code, quality="good", task="pick cup"):
    return Episode.objects.create(
        episode_id=code, robot_id="arm-01", task_name=task, recorded_at="2026-08-01T10:00:00Z",
        duration_seconds=30, operator_name="Eric", quality=quality,
    )


def make_request(client, status=S.IN_PROGRESS, episodes_requested=1):
    return DatasetRequest.objects.create(client=client, task_name="pick cup", episodes_requested=episodes_requested, deadline=TOMORROW, status=status)


def assign(request, operator, *codes):
    return [services.assign_episode(request.id, code, operator) for code in codes]


# --- Happy path through the API ---------------------------------------------------------------


def test_operator_assigns_and_unassigns_episode(operator_api, client_a):
    request = make_request(client_a)
    make_episode("EP-1")

    response = operator_api.post(f"/api/requests/{request.id}/assignments", {"episode_id": "ep-1"}, format="json")
    assert response.status_code == 201
    assert response.json()["episode"]["episode_id"] == "EP-1"
    assert response.json()["assigned_by"] == "ops1@example.com"
    assert operator_api.get(f"/api/requests/{request.id}").json()["assigned_count"] == 1
    assert [a["episode"]["episode_id"] for a in operator_api.get(f"/api/requests/{request.id}/assignments").json()] == ["EP-1"]

    assert operator_api.delete(f"/api/requests/{request.id}/assignments/EP-1").status_code == 204
    assert operator_api.get(f"/api/requests/{request.id}/assignments").json() == []
    assert operator_api.get(f"/api/requests/{request.id}").json()["assigned_count"] == 0
    assert Assignment.objects.get().unassigned_at is not None  # history is kept, not deleted


@pytest.mark.parametrize("role,expected", [("client", 403), ("operator", 201), ("admin", 201)])
def test_only_operators_and_admins_can_assign(api_for, role, expected, client_a):
    request = make_request(client_a)
    make_episode("EP-1")
    assert api_for(role).post(f"/api/requests/{request.id}/assignments", {"episode_id": "EP-1"}, format="json").status_code == expected


def test_client_can_see_own_assignments_but_not_change_them(client_a_api, client_b_api, client_a, operator):
    request = make_request(client_a)
    make_episode("EP-1")
    assign(request, operator, "EP-1")

    assert [a["episode"]["episode_id"] for a in client_a_api.get(f"/api/requests/{request.id}/assignments").json()] == ["EP-1"]
    assert client_a_api.delete(f"/api/requests/{request.id}/assignments/EP-1").status_code == 403
    assert client_b_api.get(f"/api/requests/{request.id}/assignments").status_code == 404


# --- Rules -------------------------------------------------------------------------------


def test_bad_quality_episodes_cannot_be_assigned(operator_api, client_a):
    request = make_request(client_a)
    make_episode("EP-BAD", quality="bad")

    response = operator_api.post(f"/api/requests/{request.id}/assignments", {"episode_id": "EP-BAD"}, format="json")

    assert response.status_code == 400
    assert response.json()["code"] == "episode_quality"
    assert not Assignment.objects.exists()


def test_usable_quality_can_be_assigned(client_a, operator):
    request = make_request(client_a)
    make_episode("EP-OK", quality="usable")
    assign(request, operator, "EP-OK")
    assert Assignment.objects.count() == 1


def test_episode_can_be_assigned_to_at_most_one_request_at_a_time(operator_api, client_a, client_b, operator):
    first, second = make_request(client_a), make_request(client_b)
    make_episode("EP-1")
    assign(first, operator, "EP-1")

    response = operator_api.post(f"/api/requests/{second.id}/assignments", {"episode_id": "EP-1"}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "episode_already_assigned"
    assert f"request #{first.id}" in response.json()["detail"]

    with pytest.raises(Conflict):  # the same request twice is also a conflict
        assign(first, operator, "EP-1")

    services.unassign_episode(first.id, "EP-1", operator)  # free again
    assign(second, operator, "EP-1")
    assert services.active_assignments(second).count() == 1
    assert Assignment.objects.count() == 2  # the old row stays as history


def test_database_constraint_backs_the_single_assignment_rule(client_a, client_b, operator):
    episode = make_episode("EP-1")
    a, b = make_request(client_a), make_request(client_b)
    Assignment.objects.create(request=a, episode=episode, assigned_by=operator)

    with pytest.raises(IntegrityError), transaction.atomic():
        Assignment.objects.create(request=b, episode=episode, assigned_by=operator)


@pytest.mark.parametrize("status_", [S.SUBMITTED, S.DELIVERED, S.ACCEPTED, S.REJECTED])
def test_assignments_only_change_while_in_progress(client_a, operator, status_):
    request = make_request(client_a, status=status_)
    make_episode("EP-1")

    with pytest.raises(DomainError) as exc:
        assign(request, operator, "EP-1")
    assert exc.value.code == "request_not_in_progress"


def test_assigning_unknown_episode_or_unassigning_unassigned_is_a_clear_error(operator_api, client_a):
    request = make_request(client_a)
    make_episode("EP-1")

    response = operator_api.post(f"/api/requests/{request.id}/assignments", {"episode_id": "EP-404"}, format="json")
    assert (response.status_code, response.json()["code"]) == (400, "unknown_episode")

    response = operator_api.delete(f"/api/requests/{request.id}/assignments/EP-1")
    assert (response.status_code, response.json()["code"]) == (400, "not_assigned")


# --- Delivery guard and the full lifecycle ----------------------------------------------------


def test_delivery_unlocks_once_enough_episodes_are_assigned(operator_api, client_a, operator):
    request = make_request(client_a, episodes_requested=2)
    make_episode("EP-1"), make_episode("EP-2")
    assign(request, operator, "EP-1")

    response = operator_api.post(f"/api/requests/{request.id}/transition", {"status": "delivered"}, format="json")
    assert response.json()["code"] == "not_enough_episodes" and "1 of 2" in response.json()["detail"]

    assign(request, operator, "EP-2")
    response = operator_api.post(f"/api/requests/{request.id}/transition", {"status": "delivered"}, format="json")
    assert response.status_code == 200
    assert response.json()["status"] == "delivered" and response.json()["delivered_at"] is not None


def test_full_lifecycle_with_rework(client_a, operator):
    request = services.create_request(client_a, task_name="pick cup", episodes_requested=1, deadline=TOMORROW)
    make_episode("EP-1"), make_episode("EP-2")

    services.transition(request.id, S.IN_PROGRESS, operator)
    assign(request, operator, "EP-1")
    services.transition(request.id, S.DELIVERED, operator)
    services.transition(request.id, S.REJECTED, client_a, note="wrong lighting")
    services.transition(request.id, S.IN_PROGRESS, operator)
    services.unassign_episode(request.id, "EP-1", operator)
    assign(request, operator, "EP-2")
    services.transition(request.id, S.DELIVERED, operator)
    first_delivery = DatasetRequest.objects.get(pk=request.id).delivered_at
    services.transition(request.id, S.ACCEPTED, client_a)

    request.refresh_from_db()
    assert request.status == S.ACCEPTED
    assert request.delivered_at == first_delivery  # first delivery is what fulfilment analytics measure
    assert [a.episode.episode_id for a in services.active_assignments(request)] == ["EP-2"]
    assert [(e.from_status, e.to_status, e.actor.role) for e in request.events.all()] == [
        ("", "submitted", "client"),
        ("submitted", "in_progress", "operator"),
        ("in_progress", "delivered", "operator"),
        ("delivered", "rejected", "client"),
        ("rejected", "in_progress", "operator"),
        ("in_progress", "delivered", "operator"),
        ("delivered", "accepted", "client"),
    ]


# --- Episode list integration ----------------------------------------------------------------


def test_episode_list_shows_assignment_and_available_filter(operator_api, client_a, operator):
    request = make_request(client_a)
    make_episode("EP-1"), make_episode("EP-2"), make_episode("EP-3", quality="bad")
    assign(request, operator, "EP-1")

    rows = {e["episode_id"]: e for e in operator_api.get("/api/episodes").json()["results"]}
    assert rows["EP-1"]["assigned_request_id"] == request.id
    assert rows["EP-2"]["assigned_request_id"] is None
    assert [e["episode_id"] for e in operator_api.get("/api/episodes?available=1").json()["results"]] == ["EP-2"]


def test_request_list_counts_assignments_in_one_query(operator_api, client_a, operator, django_assert_num_queries):
    for i in range(3):
        request = make_request(client_a)
        make_episode(f"EP-{i}")
        assign(request, operator, f"EP-{i}")

    with django_assert_num_queries(4):  # session, user, count, page — not one per request
        body = operator_api.get("/api/requests").json()
    assert [r["assigned_count"] for r in body["results"]] == [1, 1, 1]
