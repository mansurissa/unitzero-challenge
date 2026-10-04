"""CSV import of episode metadata.

The export is messy, so every row goes through normalise -> validate -> de-duplicate -> compare with DB.
The import is idempotent: rows already present (identical) are reported as `already_imported` and never
re-inserted; rows that differ from what is stored are reported as `conflicts_with_existing` and NOT applied,
because the database may already have assignments depending on that episode (see NOTES.md).
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from .models import Episode, ImportRun

EXPECTED_COLUMNS = ["episode_id", "robot_id", "task_name", "recorded_at", "duration_seconds", "operator_name", "quality"]

# From seed/README.md. In production this would be a Robot table maintained by ops.
KNOWN_ROBOTS = frozenset({"arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01"})

# Episodes are "short clips"; anything longer than an hour is treated as a bad export value.
MIN_DURATION_SECONDS = 1
MAX_DURATION_SECONDS = 3600

BATCH_SIZE = 1000


class RowError(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class ImportReport:
    source: str
    total_rows: int = 0
    inserted: int = 0
    skipped_rows: list = field(default_factory=list)
    warning_rows: list = field(default_factory=list)

    def skip(self, line, episode_id, reason, detail=""):
        self.skipped_rows.append({"line": line, "episode_id": episode_id, "reason": reason, "detail": detail})

    def warn(self, line, episode_id, reason, detail=""):
        self.warning_rows.append({"line": line, "episode_id": episode_id, "reason": reason, "detail": detail})

    @property
    def skipped(self):
        return len(self.skipped_rows)

    def by_reason(self):
        counts = {}
        for row in self.skipped_rows:
            counts[row["reason"]] = counts.get(row["reason"], 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self):
        return {
            "source": self.source,
            "total_rows": self.total_rows,
            "inserted": self.inserted,
            "skipped": self.skipped,
            "warnings": len(self.warning_rows),
            "skipped_by_reason": self.by_reason(),
            "skipped_rows": self.skipped_rows,
            "warning_rows": self.warning_rows,
        }


# --- Per-field normalisation ---------------------------------------------------


def _parse_recorded_at(raw):
    text = raw.strip()
    if not text:
        raise RowError("missing_recorded_at")
    parsed = None
    try:
        parsed = datetime.fromisoformat(text)  # 2026-08-14T09:12:00, 2026-08-14 09:12:00, ...T09:20:00Z, +02:00
    except ValueError:
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise RowError("invalid_recorded_at", raw)
    if parsed.tzinfo is None:
        # The recording system exports naive timestamps; we treat them as UTC (documented in NOTES.md).
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    if parsed > timezone.now():
        raise RowError("recorded_in_future", raw)
    return parsed


def _parse_duration(raw):
    text = raw.strip()
    if not text:
        raise RowError("missing_duration")
    try:
        value = int(text)
    except ValueError:
        raise RowError("invalid_duration", raw) from None
    if not MIN_DURATION_SECONDS <= value <= MAX_DURATION_SECONDS:
        raise RowError("duration_out_of_range", raw)
    return value


def normalise_row(cells, report, line):
    """Turn one raw CSV row into a dict of clean field values, or raise RowError."""
    raw = dict(zip(EXPECTED_COLUMNS, cells))

    episode_id = raw["episode_id"].strip().upper()
    if not episode_id:
        raise RowError("missing_episode_id")

    robot_id = raw["robot_id"].strip().lower()
    if not robot_id:
        raise RowError("missing_robot_id")
    if robot_id not in KNOWN_ROBOTS:
        raise RowError("unknown_robot", raw["robot_id"])

    task_name = " ".join(raw["task_name"].split()).lower()
    if not task_name:
        raise RowError("missing_task_name")

    quality = raw["quality"].strip().lower()
    if not quality:
        raise RowError("missing_quality")
    if quality not in Episode.Quality.values:
        raise RowError("invalid_quality", raw["quality"])

    operator_name = " ".join(raw["operator_name"].split())
    if not operator_name:
        report.warn(line, episode_id, "missing_operator_name")

    return {
        "episode_id": episode_id,
        "robot_id": robot_id,
        "task_name": task_name,
        "recorded_at": _parse_recorded_at(raw["recorded_at"]),
        "duration_seconds": _parse_duration(raw["duration_seconds"]),
        "operator_name": operator_name,
        "quality": quality,
    }


# --- File level ------------------------------------------------------------------


def _read_header(reader):
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("The file is empty") from None
    header = [h.strip().lower() for h in header]
    if header != EXPECTED_COLUMNS:
        raise ValueError(f"Unexpected header {header!r}; expected {EXPECTED_COLUMNS!r}")


def parse_csv(text, report):
    """Yields (line_number, clean_row) for every valid, de-duplicated row; records skips on the report."""
    reader = csv.reader(io.StringIO(text, newline=""))
    _read_header(reader)

    seen = {}  # episode_id -> clean row (first valid occurrence wins)
    for cells in reader:
        line = reader.line_num
        report.total_rows += 1

        if all(not c.strip() for c in cells):
            report.skip(line, "", "empty_row")
            continue
        if len(cells) != len(EXPECTED_COLUMNS):
            report.skip(line, cells[0].strip().upper() if cells else "", "malformed_row", f"{len(cells)} columns")
            continue
        try:
            row = normalise_row(cells, report, line)
        except RowError as exc:
            report.skip(line, cells[0].strip().upper(), exc.reason, exc.detail)
            continue

        previous = seen.get(row["episode_id"])
        if previous is not None:
            reason = "duplicate_in_file" if previous == row else "conflicting_duplicate_in_file"
            report.skip(line, row["episode_id"], reason)
            continue
        seen[row["episode_id"]] = row
        yield line, row


def _episode_matches(episode, row):
    return all(getattr(episode, name) == value for name, value in row.items())


def import_episodes(text, source="upload", user=None):
    """Import a CSV (as text). Returns the saved ImportRun. Everything happens in one transaction."""
    report = ImportReport(source=source)
    rows = list(parse_csv(text, report))

    with transaction.atomic():
        to_create = []
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            existing = Episode.objects.in_bulk([row["episode_id"] for _, row in batch], field_name="episode_id")
            for line, row in batch:
                episode = existing.get(row["episode_id"])
                if episode is None:
                    to_create.append(Episode(**row))
                elif _episode_matches(episode, row):
                    report.skip(line, row["episode_id"], "already_imported")
                else:
                    report.skip(line, row["episode_id"], "conflicts_with_existing", "stored record differs; not updated")

        Episode.objects.bulk_create(to_create, batch_size=BATCH_SIZE)
        report.inserted = len(to_create)
        report.skipped_rows.sort(key=lambda r: r["line"])

        return ImportRun.objects.create(
            started_by=user,
            source=source,
            total_rows=report.total_rows,
            inserted=report.inserted,
            skipped=report.skipped,
            report=report.to_dict(),
        )
