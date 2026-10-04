#!/bin/sh
# Container start-up: schema up to date, seed accounts in place, then serve.
set -e

python manage.py migrate --noinput

# The seed folder is mounted read-only from ./seed (see docker-compose.yml). The command is idempotent.
if [ "${SEED_ON_START:-1}" = "1" ] && [ -f /seed/users.json ]; then
  python manage.py seed_users /seed/users.json
fi

# No gunicorn access log: RequestLogMiddleware already writes one structured line per request.
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}"
