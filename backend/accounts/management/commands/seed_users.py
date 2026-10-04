import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Create or update the accounts listed in a users.json file. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path, help="Path to users.json")

    def handle(self, path, **options):
        if not path.exists():
            raise CommandError(f"{path} does not exist")
        try:
            entries = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path} is not valid JSON: {exc}") from exc

        created = updated = 0
        for entry in entries:
            email = entry["email"].strip().lower()
            fields = {
                "name": entry.get("name", ""),
                "role": entry["role"],
                "organisation": entry.get("organisation", ""),
                "is_active": True,
            }
            if fields["role"] not in User.Role.values:
                raise CommandError(f"{email}: unknown role {fields['role']!r}")

            user, was_created = User.objects.get_or_create(email=email, defaults=fields)
            if not was_created:
                for name, value in fields.items():
                    setattr(user, name, value)
            # Always (re)set the password so a changed seed file takes effect. set_password hashes it (Argon2).
            user.set_password(entry["password"])
            user.save()
            created += was_created
            updated += not was_created

        self.stdout.write(f"seed_users: {created} created, {updated} updated")
