#!/bin/sh
# Container start-up: bring the schema up to date, then serve.
set -e

python manage.py migrate --noinput

# No gunicorn access log: RequestLogMiddleware already writes one structured line per request.
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}"
