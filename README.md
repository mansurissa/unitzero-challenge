# Dataset Request Desk

Internal platform for tracking robot-teleoperation dataset requests.
Backend: Django + Django REST Framework + PostgreSQL. Frontend: React (Vite + TypeScript) served by nginx.

## Run

```bash
docker compose up --build        # or: make up
```

From a clean clone this starts PostgreSQL, applies migrations, creates the seed users, and serves:

| | URL |
|---|---|
| Web UI | http://localhost:3000 |
| API | http://localhost:8000 (also proxied at http://localhost:3000/api/…) |
| Health | http://localhost:8000/health → `{"status": "ok", "db": "ok"}` (503 if the database is unreachable) |

### Seed users

| Email | Password | Role |
|---|---|---|
| admin@example.com | admin123 | admin |
| ops1@example.com / ops2@example.com | ops123 | operator |
| client-a@example.com | client123 | client (Acme Robotics) |
| client-b@example.com | client123 | client (Beta Labs) |

Accounts come from `seed/users.json`; `seed_users` runs on every container start and is idempotent
(`SEED_ON_START=0` disables it). Passwords are hashed with Argon2; the plain-text values never reach the database.

Logs are JSON, one line per HTTP request (`method`, `path`, `status`, `duration_ms`, `user_id`): `make logs`.

## Test

```bash
make test                        # or: docker compose run --rm api pytest
```

Tests run against a real PostgreSQL (pytest-django creates and drops a `test_requestdesk` database).

## API

All endpoints except `POST /api/auth/login`, `GET /api/auth/csrf` and `/health` require a session.
Writes need the `X-CSRFToken` header (value of the `csrftoken` cookie). Errors are `{"detail": "..."}` or
`{"field": ["message"]}`.

| Method & path | Who | What |
|---|---|---|
| `POST /api/auth/login` | anyone | `{email, password}` → user; sets session + CSRF cookies |
| `POST /api/auth/logout`, `GET /api/auth/me` | any user | end session / current user |
| `GET /api/auth/csrf` | anyone | sets the CSRF cookie for a fresh browser |
| `GET /api/users`, `GET /api/users/{id}` | admin | list / view users |
| `POST /api/users` | admin | `{email, name, role, organisation?, password}` |
| `PATCH /api/users/{id}` | admin | change `name`, `role`, `organisation`, `is_active`; admins cannot deactivate or demote themselves |
| `GET /api/episodes`, `GET /api/episodes/{id}` | operator, admin | paginated (50/page), newest first; filters `?task_name=&quality=&robot_id=` |
| `GET /api/episodes/task-names` | operator, admin | distinct task names, for filter dropdowns |

Users are never deleted; deactivating keeps the audit trail intact and ends the user's session on their next request.

## Development

`make` with no target lists everything. Each target wraps a plain `docker compose` / `manage.py` / `npm` command (make prints what it runs), so nothing depends on make.

| Command | What it does |
|---|---|
| `make server` | Backend locally with auto-reload on :8000 (creates the venv and `.env`, starts Postgres, migrates). `PORT=8001` to change |
| `make web` | Frontend dev server on :5173, proxying `/api` and `/health` to :8000 |
| `make seed` | Create/update the seed accounts locally |
| `make migrations` / `make migrate` | Create / apply migrations (`APP=accounts` to limit) |
| `make test-local` | Fast test run from the venv (`ARGS="-k health"` to filter) |
| `make shell` / `make dbshell` | Django shell / psql |
| `make up` / `down` / `logs` / `reset` | Full stack in Docker (`reset` also deletes the database) |

Local mode runs Django from `backend/.venv` and only Postgres in Docker, published on `localhost:55432` to avoid clashing with a locally installed Postgres. Don't run `make server` and `make up` at the same time on port 8000.

## Layout

```
backend/
  config/     settings (all env-driven), urls, wsgi
  accounts/   custom User model (email login, role, organisation), auth views, permissions, seed_users
  episodes/   Episode model and the operator episode list
  core/       /health view, request-logging middleware
  tests/
frontend/
  src/        App.tsx (hello page that calls /health), main.tsx, index.css
  nginx.conf  serves the build, proxies /api and /health to the api container
seed/         users.json, episodes.csv (messy), generate_episodes.py
```
