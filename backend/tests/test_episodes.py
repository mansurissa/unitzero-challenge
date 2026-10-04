from datetime import datetime, timezone

import pytest
from django.db import IntegrityError

from episodes.models import Episode

pytestmark = pytest.mark.django_db


def make_episode(code, robot="arm-01", task="pick cup", quality="good", when=datetime(2026, 8, 1, 10, tzinfo=timezone.utc)):
    return Episode.objects.create(
        episode_id=code, robot_id=robot, task_name=task, recorded_at=when, duration_seconds=30, operator_name="Eric", quality=quality
    )


@pytest.fixture
def catalogue():
    make_episode("EP-1", robot="arm-01", task="pick cup", quality="good")
    make_episode("EP-2", robot="arm-02", task="pick cup", quality="bad")
    make_episode("EP-3", robot="arm-01", task="fold towel", quality="usable")


def ids(response):
    return sorted(e["episode_id"] for e in response.json()["results"])


# --- Authorization ---------------------------------------------------------------------------


@pytest.mark.parametrize("role,expected", [("operator", 200), ("admin", 200), ("client", 403)])
def test_episode_list_is_for_operators_and_admins(api_for, role, expected, catalogue):
    assert api_for(role).get("/api/episodes").status_code == expected
    assert api_for(role).get("/api/episodes/task-names").status_code == expected


def test_episode_list_requires_authentication(anon_api):
    assert anon_api.get("/api/episodes").status_code == 403


# --- Listing and filters --------------------------------------------------------------------


def test_list_is_paginated_and_newest_first(operator_api):
    make_episode("EP-OLD", when=datetime(2026, 8, 1, tzinfo=timezone.utc))
    make_episode("EP-NEW", when=datetime(2026, 8, 2, tzinfo=timezone.utc))

    body = operator_api.get("/api/episodes").json()

    assert body["count"] == 2
    assert set(body) == {"count", "next", "previous", "results"}
    assert [e["episode_id"] for e in body["results"]] == ["EP-NEW", "EP-OLD"]
    assert set(body["results"][0]) == {
        "id", "episode_id", "robot_id", "task_name", "recorded_at", "duration_seconds", "operator_name", "quality", "assigned_request_id",
    }


def test_filters(operator_api, catalogue):
    assert ids(operator_api.get("/api/episodes")) == ["EP-1", "EP-2", "EP-3"]
    assert ids(operator_api.get("/api/episodes?task_name=pick+cup")) == ["EP-1", "EP-2"]
    assert ids(operator_api.get("/api/episodes?quality=good")) == ["EP-1"]
    assert ids(operator_api.get("/api/episodes?robot_id=arm-01")) == ["EP-1", "EP-3"]
    assert ids(operator_api.get("/api/episodes?task_name=pick+cup&quality=bad")) == ["EP-2"]
    assert ids(operator_api.get("/api/episodes?task_name=nothing")) == []


def test_filters_are_normalised_like_the_stored_values(operator_api, catalogue):
    assert ids(operator_api.get("/api/episodes?task_name=++Pick++Cup+")) == ["EP-1", "EP-2"]
    assert ids(operator_api.get("/api/episodes?quality=GOOD")) == ["EP-1"]
    assert ids(operator_api.get("/api/episodes?robot_id=ARM-01")) == ["EP-1", "EP-3"]


def test_retrieve_single_episode(operator_api, catalogue):
    episode = Episode.objects.get(episode_id="EP-3")
    body = operator_api.get(f"/api/episodes/{episode.id}").json()
    assert body["episode_id"] == "EP-3" and body["quality"] == "usable"
    assert operator_api.get("/api/episodes/999999").status_code == 404


def test_task_names_are_distinct_and_sorted(operator_api, catalogue):
    assert operator_api.get("/api/episodes/task-names").json() == ["fold towel", "pick cup"]


# --- Model constraints -----------------------------------------------------------------------


def test_episode_id_is_unique():
    make_episode("EP-1")
    with pytest.raises(IntegrityError):
        make_episode("EP-1")
