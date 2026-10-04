import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User

pytestmark = pytest.mark.django_db

SEED_FILE = Path(__file__).resolve().parents[2] / "seed" / "users.json"


def test_seed_file_creates_all_accounts_with_hashed_passwords():
    out = StringIO()
    call_command("seed_users", SEED_FILE, stdout=out)

    entries = json.loads(SEED_FILE.read_text())
    assert User.objects.count() == len(entries) == 5
    assert "5 created, 0 updated" in out.getvalue()
    for entry in entries:
        user = User.objects.get(email=entry["email"])
        assert user.role == entry["role"]
        assert user.name == entry["name"]
        assert user.organisation == entry.get("organisation", "")
        assert user.is_active
        assert user.password != entry["password"]
        assert user.password.startswith("argon2")
        assert user.check_password(entry["password"])


def test_running_twice_creates_no_duplicates():
    call_command("seed_users", SEED_FILE)
    out = StringIO()
    call_command("seed_users", SEED_FILE, stdout=out)

    assert User.objects.count() == 5
    assert "0 created, 5 updated" in out.getvalue()


def test_rerun_applies_changes_and_reactivates(tmp_path):
    seed = tmp_path / "users.json"
    seed.write_text(json.dumps([{"email": "Ops@Example.com", "password": "first", "role": "operator", "name": "Olu"}]))
    call_command("seed_users", seed)
    user = User.objects.get(email="ops@example.com")  # lowercased
    user.is_active = False
    user.save()

    seed.write_text(json.dumps([{"email": "ops@example.com", "password": "second", "role": "admin", "name": "Olu A."}]))
    call_command("seed_users", seed)

    user.refresh_from_db()
    assert (user.role, user.name, user.is_active) == ("admin", "Olu A.", True)
    assert user.check_password("second") and not user.check_password("first")


def test_unknown_role_and_missing_file_fail_cleanly(tmp_path):
    seed = tmp_path / "users.json"
    seed.write_text(json.dumps([{"email": "x@example.com", "password": "pw", "role": "superuser", "name": "X"}]))
    with pytest.raises(CommandError, match="unknown role"):
        call_command("seed_users", seed)
    assert User.objects.count() == 0

    with pytest.raises(CommandError, match="does not exist"):
        call_command("seed_users", tmp_path / "missing.json")
