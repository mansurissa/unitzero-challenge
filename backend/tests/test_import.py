"""CSV import: idempotency, handling of every messy case in seed/episodes.csv, and the command."""

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from episodes.importer import import_episodes
from episodes.models import Episode, ImportRun

pytestmark = pytest.mark.django_db

SEED_CSV = Path(__file__).resolve().parents[2] / "seed" / "episodes.csv"
HEADER = "episode_id,robot_id,task_name,recorded_at,duration_seconds,operator_name,quality\n"


def seed_text():
    return SEED_CSV.read_text(encoding="utf-8-sig")


def csv_of(*rows):
    return HEADER + "".join(r + "\n" for r in rows)


def reasons_by_line(run):
    return {row["line"]: row["reason"] for row in run.report["skipped_rows"]}


# --- Idempotency -------------------------------------------------------------------


def test_importing_the_seed_file_twice_creates_no_duplicates(operator):
    first = import_episodes(seed_text(), source="episodes.csv", user=operator)
    count_after_first = Episode.objects.count()

    second = import_episodes(seed_text(), source="episodes.csv", user=operator)

    assert first.inserted == count_after_first > 0
    assert second.inserted == 0
    assert Episode.objects.count() == count_after_first
    assert second.report["skipped_by_reason"]["already_imported"] == first.inserted
    # The messy rows are reported identically on every run.
    assert {k: v for k, v in second.report["skipped_by_reason"].items() if k != "already_imported"} == first.report["skipped_by_reason"]
    assert ImportRun.objects.count() == 2


def test_seed_file_counts():
    run = import_episodes(seed_text())

    assert run.total_rows == 191
    assert run.inserted == 172
    assert run.skipped == 19
    assert run.report["skipped_by_reason"] == {
        "conflicting_duplicate_in_file": 2,
        "duplicate_in_file": 2,
        "duration_out_of_range": 2,
        "empty_row": 2,
        "invalid_duration": 2,
        "invalid_quality": 1,
        "invalid_recorded_at": 1,
        "malformed_row": 1,
        "missing_duration": 1,
        "missing_episode_id": 1,
        "missing_quality": 1,
        "missing_robot_id": 1,
        "recorded_in_future": 1,
        "unknown_robot": 1,
    }
    assert run.report["warning_rows"] == [{"line": 190, "episode_id": "EP-90005", "reason": "missing_operator_name", "detail": ""}]


# --- Each messy case gets the right reason ---------------------------------------------


def test_seed_file_skip_reasons_are_attributed_to_the_right_lines():
    run = import_episodes(seed_text())

    assert reasons_by_line(run) == {
        50: "duplicate_in_file",                 # EP-00074 appears twice, identical
        59: "missing_episode_id",
        66: "invalid_duration",                  # 45.5
        69: "missing_quality",
        79: "invalid_quality",                   # excellent
        91: "duplicate_in_file",                 # EP-00030 appears twice, identical
        95: "missing_duration",
        100: "duration_out_of_range",            # -5
        113: "recorded_in_future",               # 2031
        131: "invalid_recorded_at",              # "not a date"
        162: "unknown_robot",                    # arm-99
        168: "conflicting_duplicate_in_file",    # EP-00011 bad vs good
        170: "missing_robot_id",
        185: "malformed_row",                    # 5 columns
        187: "invalid_duration",                 # N/A
        188: "duration_out_of_range",            # 999999
        189: "conflicting_duplicate_in_file",    # ep-00003 lower-case id, different data from EP-00003
        191: "empty_row",
        192: "empty_row",
    }


def test_values_are_normalised_on_import():
    import_episodes(seed_text())
    by_id = {e.episode_id: e for e in Episode.objects.all()}

    assert by_id["EP-00008"].robot_id == "arm-01"                 # leading space
    assert by_id["EP-00006"].task_name == "pick cup"              # "  Pick Cup "
    assert by_id["EP-00007"].task_name == "pick cup"              # PICK CUP
    assert by_id["EP-00009"].quality == "good"                    # Good
    assert by_id["EP-00010"].quality == "usable"                  # USABLE
    assert by_id["EP-00014"].recorded_at == datetime(2026, 8, 14, 9, 15, tzinfo=timezone.utc)   # 14/08/2026 09:15
    assert by_id["EP-00013"].recorded_at == datetime(2026, 8, 14, 9, 12, tzinfo=timezone.utc)   # space separator
    assert by_id["EP-00015"].recorded_at == datetime(2026, 8, 14, 9, 20, tzinfo=timezone.utc)   # trailing Z
    assert by_id["EP-90002"].task_name == "pick cup, then place"  # quoted field containing a comma
    assert by_id["EP-90005"].operator_name == ""                  # missing operator is allowed
    assert by_id["EP-00011"].quality == "bad"                     # first occurrence wins
    assert "EP-00003" in by_id and by_id["EP-00003"].robot_id == "humanoid-01"


def test_existing_record_is_never_overwritten_by_a_conflicting_row():
    import_episodes(csv_of("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Eric,good"))

    run = import_episodes(csv_of("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Eric,bad"))

    assert run.inserted == 0
    assert reasons_by_line(run) == {2: "conflicts_with_existing"}
    assert Episode.objects.get(episode_id="EP-1").quality == "good"


def test_invalid_rows_do_not_block_valid_ones_and_run_is_recorded(operator):
    run = import_episodes(
        csv_of("EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Eric,good", "EP-2,arm-01,pick cup,garbage,30,Eric,good"),
        source="x.csv",
        user=operator,
    )
    assert run.inserted == 1 and run.skipped == 1
    assert run.started_by == operator and run.source == "x.csv"


@pytest.mark.parametrize("header", ["episode_id,robot_id\n", "", "a,b,c,d,e,f,g\n"])
def test_wrong_header_is_rejected_before_touching_the_database(header):
    with pytest.raises(ValueError):
        import_episodes(header + "EP-1,arm-01,pick cup,2026-08-01T10:00:00,30,Eric,good\n")
    assert Episode.objects.count() == 0 and ImportRun.objects.count() == 0


# --- Management command --------------------------------------------------------------------


def test_command_imports_and_prints_summary(admin):
    out = StringIO()
    call_command("import_episodes", SEED_CSV, user="Admin@Example.com", stdout=out)

    assert Episode.objects.count() == 172
    text = out.getvalue()
    assert "172 inserted, 19 skipped, 1 warnings" in text
    assert "unknown_robot: 1" in text
    assert "line 162 EP-00024: unknown_robot (arm-99)" in text
    assert ImportRun.objects.get().started_by == admin


def test_command_fails_cleanly(tmp_path):
    with pytest.raises(CommandError, match="does not exist"):
        call_command("import_episodes", tmp_path / "missing.csv")
    bad = tmp_path / "bad.csv"
    bad.write_text("not,a,valid,header\n")
    with pytest.raises(CommandError, match="Unexpected header"):
        call_command("import_episodes", bad)
    with pytest.raises(CommandError, match="No user"):
        call_command("import_episodes", SEED_CSV, user="nobody@example.com")
    assert Episode.objects.count() == 0
