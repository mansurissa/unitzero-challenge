import pytest

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db

LOGIN = "/api/auth/login"


def test_login_with_valid_credentials_returns_user_and_sets_cookies(anon_api, client_a):
    response = anon_api.post(LOGIN, {"email": "client-a@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["email"] == "client-a@example.com"
    assert response.json()["role"] == "client"
    assert "password" not in response.json()
    assert "sessionid" in response.cookies
    assert "csrftoken" in response.cookies
    # the session works for the next request
    assert anon_api.get("/api/auth/me").json()["id"] == client_a.id


def test_login_email_is_case_insensitive(anon_api, client_a):
    response = anon_api.post(LOGIN, {"email": "  Client-A@Example.com ", "password": PASSWORD})
    assert response.status_code == 200


def test_login_with_wrong_password_fails_without_a_session(anon_api, client_a):
    response = anon_api.post(LOGIN, {"email": "client-a@example.com", "password": "nope"})

    assert response.status_code == 400
    assert "sessionid" not in response.cookies
    assert anon_api.get("/api/auth/me").status_code == 403


def test_login_with_unknown_email_gives_the_same_error_as_wrong_password(anon_api, client_a):
    unknown = anon_api.post(LOGIN, {"email": "nobody@example.com", "password": PASSWORD}).json()
    wrong = anon_api.post(LOGIN, {"email": "client-a@example.com", "password": "nope"}).json()
    assert unknown == wrong  # no account enumeration


def test_login_validates_input(anon_api):
    assert anon_api.post(LOGIN, {"email": "not-an-email", "password": "x"}).status_code == 400
    assert anon_api.post(LOGIN, {"email": "a@example.com"}).status_code == 400


def test_deactivated_user_cannot_log_in(anon_api, client_a):
    client_a.is_active = False
    client_a.save()

    assert anon_api.post(LOGIN, {"email": "client-a@example.com", "password": PASSWORD}).status_code == 400


def test_deactivating_a_user_ends_their_existing_session(client_a_api, client_a):
    assert client_a_api.get("/api/auth/me").status_code == 200

    client_a.is_active = False
    client_a.save()

    assert client_a_api.get("/api/auth/me").status_code == 403


def test_logout_ends_the_session(client_a_api):
    assert client_a_api.post("/api/auth/logout").status_code == 204
    assert client_a_api.get("/api/auth/me").status_code == 403


def test_csrf_endpoint_is_public_and_sets_the_cookie(anon_api):
    response = anon_api.get("/api/auth/csrf")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies


@pytest.mark.parametrize("method,path", [("get", "/api/auth/me"), ("post", "/api/auth/logout")])
def test_everything_except_login_and_csrf_requires_authentication(anon_api, method, path):
    assert getattr(anon_api, method)(path).status_code == 403


def test_me_returns_the_logged_in_user(operator_api, operator):
    body = operator_api.get("/api/auth/me").json()
    assert body["id"] == operator.id
    assert body["role"] == "operator"
