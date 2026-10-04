"""Request workflow: creation, client isolation, status transitions by role, audit trail."""

from datetime import date, timedelta

import pytest

from core.exceptions import NotAllowed
from dataset_requests import services
from dataset_requests.models import DatasetRequest, StatusEvent

pytestmark = pytest.mark.django_db

S = DatasetRequest.Status
TOMORROW = date.today() + timedelta(days=1)


def make_request(client, status=S.SUBMITTED, episodes_requested=1, task="pick cup"):
    """Test setup shortcut: writes the status directly. Transition rules themselves are tested through the service."""
    return DatasetRequest.objects.create(
        client=client, task_name=task, episodes_requested=episodes_requested, deadline=TOMORROW, status=status
    )


# --- Creation and visibility -------------------------------------------------------------


def test_client_creates_request_and_initial_event_is_recorded(client_a_api, client_a):
    payload = {"task_name": "  Pick  Cup ", "episodes_requested": 3, "deadline": TOMORROW.isoformat(), "notes": "asap"}

    response = client_a_api.post("/api/requests", payload, format="json")

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "submitted"
    assert body["task_name"] == "pick cup"
    assert body["assigned_count"] == 0
    assert body["client"]["email"] == "client-a@example.com"
    assert body["allowed_transitions"] == []  # nothing a client can do with a fresh request
    [event] = StatusEvent.objects.filter(request_id=body["id"])
    assert (event.from_status, event.to_status, event.actor) == ("", "submitted", client_a)


@pytest.mark.parametrize("role,expected", [("client", 201), ("operator", 403), ("admin", 403)])
def test_only_clients_can_create_requests(api_for, role, expected):
    payload = {"task_name": "pick cup", "episodes_requested": 1, "deadline": TOMORROW.isoformat()}
    assert api_for(role).post("/api/requests", payload, format="json").status_code == expected


@pytest.mark.parametrize("bad", [
    {"episodes_requested": 0},
    {"episodes_requested": -2},
    {"task_name": "   "},
    {"deadline": (date.today() - timedelta(days=1)).isoformat()},
    {"deadline": "not-a-date"},
])
def test_request_validation(client_a_api, bad):
    payload = {"task_name": "pick cup", "episodes_requested": 1, "deadline": TOMORROW.isoformat(), **bad}
    assert client_a_api.post("/api/requests", payload, format="json").status_code == 400
    assert DatasetRequest.objects.count() == 0


def test_clients_see_only_their_own_requests(client_a_api, client_a, client_b):
    mine = make_request(client_a)
    theirs = make_request(client_b)

    assert [r["id"] for r in client_a_api.get("/api/requests").json()["results"]] == [mine.id]
    assert client_a_api.get(f"/api/requests/{mine.id}").status_code == 200
    assert client_a_api.get(f"/api/requests/{theirs.id}").status_code == 404
    assert client_a_api.get(f"/api/requests/{theirs.id}/history").status_code == 404


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_operators_and_admins_see_all_requests(api_for, role, client_a, client_b):
    a, b = make_request(client_a), make_request(client_b)
    ids = {r["id"] for r in api_for(role).get("/api/requests").json()["results"]}
    assert ids == {a.id, b.id}


def test_list_filters(operator_api, client_a, client_b):
    make_request(client_a, status=S.SUBMITTED)
    in_progress = make_request(client_a, status=S.IN_PROGRESS)
    make_request(client_b, status=S.IN_PROGRESS)

    assert [r["id"] for r in operator_api.get("/api/requests?status=in_progress&client=" + str(client_a.id)).json()["results"]] == [in_progress.id]
    assert operator_api.get("/api/requests?status=submitted").json()["count"] == 1


def test_unauthenticated_requests_are_rejected(anon_api, client_a):
    r = make_request(client_a)
    assert anon_api.get("/api/requests").status_code == 403
    assert anon_api.post(f"/api/requests/{r.id}/transition", {"status": "in_progress"}).status_code == 403


# --- Status transitions ------------------------------------------------------------------

VALID_MOVES = [
    (S.SUBMITTED, S.IN_PROGRESS, "operator"),
    (S.SUBMITTED, S.IN_PROGRESS, "admin"),
    (S.DELIVERED, S.ACCEPTED, "client"),
    (S.DELIVERED, S.REJECTED, "client"),
    (S.REJECTED, S.IN_PROGRESS, "operator"),
    (S.REJECTED, S.IN_PROGRESS, "admin"),
]


@pytest.mark.parametrize("frm,to,role", VALID_MOVES)
def test_valid_transitions_by_the_owning_role(api_for, client_a, frm, to, role):
    request = make_request(client_a, status=frm)

    response = api_for(role).post(f"/api/requests/{request.id}/transition", {"status": to, "note": "ok"}, format="json")

    assert response.status_code == 200, response.json()
    assert response.json()["status"] == to
    event = StatusEvent.objects.get(request=request)
    assert (event.from_status, event.to_status, event.note) == (frm, to, "ok")
    assert event.actor.role == role


WRONG_ROLE_MOVES = [
    (S.SUBMITTED, S.IN_PROGRESS, "client"),
    (S.IN_PROGRESS, S.DELIVERED, "client"),
    (S.DELIVERED, S.ACCEPTED, "operator"),
    (S.DELIVERED, S.ACCEPTED, "admin"),
    (S.DELIVERED, S.REJECTED, "operator"),
    (S.REJECTED, S.IN_PROGRESS, "client"),
]


@pytest.mark.parametrize("frm,to,role", WRONG_ROLE_MOVES)
def test_valid_transition_by_the_wrong_role_is_forbidden(api_for, client_a, frm, to, role):
    request = make_request(client_a, status=frm)

    response = api_for(role).post(f"/api/requests/{request.id}/transition", {"status": to}, format="json")

    assert response.status_code == 403
    assert response.json()["code"] == "not_allowed"
    request.refresh_from_db()
    assert request.status == frm
    assert not StatusEvent.objects.filter(request=request).exists()


INVALID_MOVES = [
    (S.SUBMITTED, S.DELIVERED, "operator"),
    (S.SUBMITTED, S.ACCEPTED, "client"),
    (S.IN_PROGRESS, S.ACCEPTED, "client"),
    (S.IN_PROGRESS, S.SUBMITTED, "operator"),
    (S.ACCEPTED, S.REJECTED, "client"),
    (S.ACCEPTED, S.IN_PROGRESS, "operator"),
    (S.REJECTED, S.DELIVERED, "operator"),
    (S.DELIVERED, S.DELIVERED, "operator"),
]


@pytest.mark.parametrize("frm,to,role", INVALID_MOVES)
def test_invalid_transitions_are_rejected_for_everyone(api_for, client_a, frm, to, role):
    request = make_request(client_a, status=frm)

    response = api_for(role).post(f"/api/requests/{request.id}/transition", {"status": to}, format="json")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_transition"
    request.refresh_from_db()
    assert request.status == frm


def test_unknown_status_value_is_a_validation_error(operator_api, client_a):
    request = make_request(client_a)
    assert operator_api.post(f"/api/requests/{request.id}/transition", {"status": "done"}, format="json").status_code == 400


def test_client_cannot_act_on_another_clients_request(client_b_api, client_a, client_b):
    request = make_request(client_a, status=S.DELIVERED)

    assert client_b_api.post(f"/api/requests/{request.id}/transition", {"status": "accepted"}, format="json").status_code == 404
    with pytest.raises(NotAllowed):  # the service refuses too, even if a view forgot to filter
        services.transition(request.id, S.ACCEPTED, client_b)


def test_delivery_requires_enough_assigned_episodes(operator_api, client_a):
    request = make_request(client_a, status=S.IN_PROGRESS, episodes_requested=2)

    response = operator_api.post(f"/api/requests/{request.id}/transition", {"status": "delivered"}, format="json")

    assert response.status_code == 400
    assert response.json()["code"] == "not_enough_episodes"
    assert "0 of 2" in response.json()["detail"]
    request.refresh_from_db()
    assert request.status == S.IN_PROGRESS and request.delivered_at is None


def test_lifecycle_with_rejection_records_every_step(client_a, operator):
    request = services.create_request(client_a, task_name="pick cup", episodes_requested=1, deadline=TOMORROW)
    services.transition(request.id, S.IN_PROGRESS, operator)
    # Deliver by hand (assignments come later); the trail and rework path are what matter here.
    DatasetRequest.objects.filter(pk=request.id).update(status=S.DELIVERED)
    services.transition(request.id, S.REJECTED, client_a, note="wrong lighting")
    services.transition(request.id, S.IN_PROGRESS, operator)

    request.refresh_from_db()
    assert request.status == S.IN_PROGRESS
    trail = [(e.from_status, e.to_status, e.actor.role, e.note) for e in request.events.all()]
    assert trail == [
        ("", "submitted", "client", ""),
        ("submitted", "in_progress", "operator", ""),
        ("delivered", "rejected", "client", "wrong lighting"),
        ("rejected", "in_progress", "operator", ""),
    ]


def test_allowed_transitions_reflect_role_and_state(client_a_api, operator_api, client_a):
    delivered = make_request(client_a, status=S.DELIVERED)
    submitted = make_request(client_a, status=S.SUBMITTED)

    assert client_a_api.get(f"/api/requests/{delivered.id}").json()["allowed_transitions"] == ["accepted", "rejected"]
    assert operator_api.get(f"/api/requests/{delivered.id}").json()["allowed_transitions"] == []
    assert client_a_api.get(f"/api/requests/{submitted.id}").json()["allowed_transitions"] == []
    assert operator_api.get(f"/api/requests/{submitted.id}").json()["allowed_transitions"] == ["in_progress"]


def test_history_endpoint_lists_events_in_order(client_a_api, client_a, operator):
    request = services.create_request(client_a, task_name="pick cup", episodes_requested=1, deadline=TOMORROW)
    services.transition(request.id, S.IN_PROGRESS, operator, note="on it")

    body = client_a_api.get(f"/api/requests/{request.id}/history").json()

    assert [(e["from_status"], e["to_status"], e["actor"], e["note"]) for e in body] == [
        ("", "submitted", "client-a@example.com", ""),
        ("submitted", "in_progress", "ops1@example.com", "on it"),
    ]
