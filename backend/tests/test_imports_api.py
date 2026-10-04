import pytest

from episodes.importer import import_episodes

pytestmark = pytest.mark.django_db

HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"


@pytest.mark.parametrize("role,expected", [("operator", 200), ("admin", 200), ("client", 403)])
def test_import_runs_are_visible_to_operators_and_admins(api_for, role, expected):
    assert api_for(role).get("/api/imports").status_code == expected


def test_import_runs_list_newest_first_with_report(operator_api, operator):
    import_episodes(HEADER + "EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Eric,good\n", source="first.csv", user=operator)
    import_episodes(HEADER + "EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Eric,good\nEP-2,arm-99,x,2026-08-01T10:00:00,30,Eric,good\n", source="second.csv")

    body = operator_api.get("/api/imports").json()

    assert [r["source"] for r in body["results"]] == ["second.csv", "first.csv"]
    second, first = body["results"]
    assert first["started_by"] == "ops1@example.com" and first["inserted"] == 1
    assert second["started_by"] is None
    assert (second["inserted"], second["skipped"]) == (0, 2)
    assert second["report"]["skipped_by_reason"] == {"already_imported": 1, "unknown_robot": 1}
    assert operator_api.get(f"/api/imports/{first['id']}").json()["report"]["inserted"] == 1
