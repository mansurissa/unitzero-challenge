"""Shared fixtures: one user per role, and API clients already logged in as each of them."""

import pytest
from rest_framework.test import APIClient

from accounts.models import User

PASSWORD = "password123"


def make_user(email, role, name=None, organisation=""):
    return User.objects.create_user(email, PASSWORD, name=name or email.split("@")[0], role=role, organisation=organisation)


def logged_in(user):
    api = APIClient()
    api.force_login(user)
    return api


@pytest.fixture
def admin():
    return make_user("admin@example.com", User.Role.ADMIN, "Ada Admin")


@pytest.fixture
def operator():
    return make_user("ops1@example.com", User.Role.OPERATOR, "Olu Operator")


@pytest.fixture
def client_a():
    return make_user("client-a@example.com", User.Role.CLIENT, "Acme Robotics", "Acme Robotics")


@pytest.fixture
def client_b():
    return make_user("client-b@example.com", User.Role.CLIENT, "Beta Labs", "Beta Labs")


@pytest.fixture
def anon_api():
    return APIClient()


@pytest.fixture
def admin_api(admin):
    return logged_in(admin)


@pytest.fixture
def operator_api(operator):
    return logged_in(operator)


@pytest.fixture
def client_a_api(client_a):
    return logged_in(client_a)


@pytest.fixture
def client_b_api(client_b):
    return logged_in(client_b)


@pytest.fixture
def api_for(admin, operator, client_a):
    """Look up a logged-in client by role name; handy for parametrised authorization tests."""
    users = {"admin": admin, "operator": operator, "client": client_a}
    return lambda role: logged_in(users[role])
