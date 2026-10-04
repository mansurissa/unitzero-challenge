"""Admin-only user management and the role permission classes."""

import pytest

from accounts.models import User

pytestmark = pytest.mark.django_db

NEW_USER = {"email": "new@example.com", "name": "New Person", "role": "operator", "password": "longenough"}


# --- Authorization matrix -----------------------------------------------------------------


@pytest.mark.parametrize("role,expected", [("admin", 200), ("operator", 403), ("client", 403)])
def test_only_admin_can_list_users(api_for, role, expected):
    assert api_for(role).get("/api/users").status_code == expected


@pytest.mark.parametrize("role,expected", [("admin", 200), ("operator", 403), ("client", 403)])
def test_only_admin_can_view_a_user(api_for, role, expected, client_b):
    assert api_for(role).get(f"/api/users/{client_b.id}").status_code == expected


@pytest.mark.parametrize("role,expected", [("admin", 201), ("operator", 403), ("client", 403)])
def test_only_admin_can_create_users(api_for, role, expected):
    response = api_for(role).post("/api/users", NEW_USER)

    assert response.status_code == expected
    assert User.objects.filter(email="new@example.com").exists() == (expected == 201)


@pytest.mark.parametrize("role,expected", [("admin", 200), ("operator", 403), ("client", 403)])
def test_only_admin_can_update_users(api_for, role, expected, client_b):
    response = api_for(role).patch(f"/api/users/{client_b.id}", {"role": "operator"}, format="json")

    assert response.status_code == expected
    client_b.refresh_from_db()
    assert client_b.role == ("operator" if expected == 200 else "client")


def test_user_endpoints_require_authentication(anon_api, client_b):
    assert anon_api.get("/api/users").status_code == 403
    assert anon_api.post("/api/users", NEW_USER).status_code == 403
    assert anon_api.patch(f"/api/users/{client_b.id}", {"role": "admin"}, format="json").status_code == 403


def test_users_cannot_be_deleted(admin_api, client_b):
    assert admin_api.delete(f"/api/users/{client_b.id}").status_code == 405
    assert User.objects.filter(pk=client_b.id).exists()


# --- Create ------------------------------------------------------------------------------------


def test_admin_creates_user_with_hashed_password(admin_api):
    response = admin_api.post("/api/users", {**NEW_USER, "email": "  New@Example.com "})

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "password" not in body
    user = User.objects.get(email="new@example.com")
    assert user.role == "operator" and user.is_active
    assert user.password != "longenough" and user.check_password("longenough")


def test_create_rejects_duplicate_email_case_insensitively(admin_api, client_a):
    response = admin_api.post("/api/users", {**NEW_USER, "email": "CLIENT-A@example.com"})
    assert response.status_code == 400
    assert "email" in response.json()


@pytest.mark.parametrize("bad", [{"password": "short"}, {"role": "superuser"}, {"email": "not-an-email"}, {"name": ""}])
def test_create_validates_fields(admin_api, bad):
    assert admin_api.post("/api/users", {**NEW_USER, **bad}).status_code == 400
    assert not User.objects.filter(email=NEW_USER["email"]).exists()


# --- Update ------------------------------------------------------------------------------------


def test_admin_changes_role_and_deactivates(admin_api, client_a):
    response = admin_api.patch(f"/api/users/{client_a.id}", {"role": "operator", "is_active": False}, format="json")

    assert response.status_code == 200
    assert response.json()["role"] == "operator" and response.json()["is_active"] is False
    client_a.refresh_from_db()
    assert client_a.role == "operator" and client_a.is_active is False


def test_deactivated_user_loses_access_immediately(admin_api, client_a_api, client_a):
    assert client_a_api.get("/api/auth/me").status_code == 200
    admin_api.patch(f"/api/users/{client_a.id}", {"is_active": False}, format="json")
    assert client_a_api.get("/api/auth/me").status_code == 403


def test_email_and_password_are_not_editable_through_patch(admin_api, client_a):
    admin_api.patch(f"/api/users/{client_a.id}", {"email": "x@example.com", "password": "newpassword1"}, format="json")

    client_a.refresh_from_db()
    assert client_a.email == "client-a@example.com"
    assert client_a.check_password("password123")


def test_admin_cannot_lock_themselves_out(admin_api, admin):
    assert admin_api.patch(f"/api/users/{admin.id}", {"is_active": False}, format="json").status_code == 400
    assert admin_api.patch(f"/api/users/{admin.id}", {"role": "client"}, format="json").status_code == 400

    admin.refresh_from_db()
    assert admin.is_active and admin.role == "admin"
    # changing their own name is still fine
    assert admin_api.patch(f"/api/users/{admin.id}", {"name": "Ada"}, format="json").status_code == 200
