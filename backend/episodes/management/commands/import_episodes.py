import json as jsonlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from episodes.importer import import_episodes


class Command(BaseCommand):
    help = "Import episode metadata from a CSV export. Safe to re-run on the same file."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
        parser.add_argument("--user", help="Email of the user to record as the importer")
        parser.add_argument("--json", action="store_true", help="Print the full report as JSON")

    def handle(self, path, user, json, **options):
        if not path.exists():
            raise CommandError(f"{path} does not exist")
        actor = None
        if user:
            try:
                actor = User.objects.get(email=user.strip().lower())
            except User.DoesNotExist:
                raise CommandError(f"No user with email {user}") from None

        try:
            text = path.read_text(encoding="utf-8-sig")  # -sig strips a BOM if the export has one
            run = import_episodes(text, source=path.name, user=actor)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CommandError(str(exc)) from exc

        report = run.report
        if json:
            self.stdout.write(jsonlib.dumps(report, indent=2))
            return
        self.stdout.write(
            f"import_episodes: {report['total_rows']} rows read, {report['inserted']} inserted, "
            f"{report['skipped']} skipped, {report['warnings']} warnings (run #{run.id})"
        )
        for reason, count in report["skipped_by_reason"].items():
            self.stdout.write(f"  {reason}: {count}")
        for row in report["skipped_rows"]:
            detail = f" ({row['detail']})" if row["detail"] else ""
            self.stdout.write(f"    line {row['line']} {row['episode_id'] or '-'}: {row['reason']}{detail}")
        for row in report["warning_rows"]:
            self.stdout.write(f"  warning line {row['line']} {row['episode_id']}: {row['reason']}")
