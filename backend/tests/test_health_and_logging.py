from unittest import mock

import pytest
from django.db import OperationalError

from accounts.models import User

pytestmark = pytest.mark.django_db


def request_log_records(caplog):
    return [r.msg for r in caplog.records if r.name == "request"]


def test_health_ok_without_authentication(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_reports_503_when_database_is_down(client):
    with mock.patch("core.views.connection") as conn:
        conn.cursor.side_effect = OperationalError("db down")
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["db"] == "unavailable"


def test_one_log_line_per_request_with_required_fields(client, caplog):
    caplog.set_level("INFO")

    client.get("/health")

    [line] = request_log_records(caplog)
    assert line["method"] == "GET"
    assert line["path"] == "/health"
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["user_id"] is None


def test_log_line_includes_user_id_when_authenticated(client, caplog):
    user = User.objects.create_user("ops@example.com", "pw", name="Ops", role=User.Role.OPERATOR)
    client.force_login(user)
    caplog.set_level("INFO")

    client.get("/health")

    [line] = request_log_records(caplog)
    assert line["user_id"] == user.pk


def test_log_line_for_unknown_path_has_404_status(client, caplog):
    caplog.set_level("INFO")

    client.get("/does-not-exist")

    [line] = request_log_records(caplog)
    assert line["status"] == 404


def test_create_user_lowercases_email_and_hashes_password():
    user = User.objects.create_user("Client-A@Example.com", "client123", name="Acme")

    assert user.email == "client-a@example.com"
    assert user.password != "client123"
    assert user.check_password("client123")
    assert user.role == User.Role.CLIENT
