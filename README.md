# Dataset Request Desk

Internal platform for tracking robot-teleoperation dataset requests.
Backend: Django + Django REST Framework + PostgreSQL. Frontend: React (Vite + TypeScript) served by nginx.

## Run

```bash
docker compose up --build        # or: make up
```

From a clean clone this starts PostgreSQL, applies migrations, creates the seed users, imports `seed/episodes.csv`, and serves:

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
| `GET /api/episodes`, `GET /api/episodes/{id}` | operator, admin | paginated (50/page), newest first; filters `?task_name=&quality=&robot_id=&available=1`; each row carries `assigned_request_id` |
| `GET /api/episodes/task-names` | operator, admin | distinct task names, for filter dropdowns |
| `GET /api/imports`, `GET /api/imports/{id}` | operator, admin | past CSV imports with their full reports |
| `GET /api/requests`, `GET /api/requests/{id}` | client (own only), operator, admin | `?status=&client=` filters; another client's id → 404 |
| `POST /api/requests` | client | `{task_name, episodes_requested, deadline, notes?}` |
| `POST /api/requests/{id}/transition` | per transition table below | `{status, note?}` → 400 `invalid_transition`, 403 `not_allowed`, 400 `not_enough_episodes` |
| `GET /api/requests/{id}/history` | owner client, operator, admin | status events with actor and timestamp |
| `GET /api/requests/{id}/assignments` | owner client, operator, admin | episodes currently assigned |
| `POST /api/requests/{id}/assignments` | operator, admin | `{episode_id}` → 400 `episode_quality` / `request_not_in_progress` / `unknown_episode`, 409 `episode_already_assigned` |
| `DELETE /api/requests/{id}/assignments/{episode_id}` | operator, admin | unassign (the row is kept with `unassigned_at`) |
| `GET /api/analytics?from=YYYY-MM-DD&to=YYYY-MM-DD` | operator, admin | see Analytics below |

Users are never deleted; deactivating keeps the audit trail intact and ends the user's session on their next request.

### Request workflow

```
submitted → in_progress → delivered → accepted
   (ops)        (ops)        (client) ↘ rejected → in_progress  (ops, rework)
                                         (client)
```

Only these moves exist, and only the named roles may make them; the server enforces both. Moving to
`delivered` requires at least `episodes_requested` assigned episodes. Episodes can be assigned or removed only
while the request is `in_progress`; only `good`/`usable` episodes are assignable; an episode belongs to at most one
request at a time, enforced by a partial unique index in PostgreSQL (`UNIQUE (episode_id) WHERE unassigned_at IS NULL`).
On rejection the assignments are kept so the operator replaces only what was complained about. Every change writes a `StatusEvent`
(from, to, who, when, note). Responses include `allowed_transitions` for the current user so the UI shows only
the buttons that will succeed. `delivered_at` records the first delivery; rework does not reset it.

## CSV import

```bash
make import FILE=seed/episodes.csv                                            # local
docker compose exec api python manage.py import_episodes /seed/episodes.csv   # in Docker (also runs on start-up)
```

Rows are normalised (whitespace, casing, several timestamp formats; naive timestamps are treated as UTC) and
validated (known robot, valid quality, integer duration 1–3600 s, date not in the future). The command prints a
summary and every skipped line with its reason: `empty_row`, `malformed_row`, `missing_*`, `invalid_*`,
`unknown_robot`, `recorded_in_future`, `duration_out_of_range`, `duplicate_in_file`,
`conflicting_duplicate_in_file`, `already_imported`, `conflicts_with_existing`.

Running the same file again inserts nothing. A row that differs from a stored episode is **reported, not
applied** (see NOTES.md). Each run is saved as an `ImportRun` and visible at `/api/imports`.

The seed file: 191 rows → 172 imported, 19 skipped, 1 warning (missing operator name, imported anyway).

## Analytics

`GET /api/analytics?from=&to=` (inclusive dates, default last 30 days) returns:

- `episodes_per_day_per_robot`: `GROUP BY date_trunc('day', recorded_at), robot_id`
- `requests.by_status` and `requests.median_submitted_to_delivered_seconds`: `COUNT … GROUP BY status` and
  `percentile_cont(0.5) WITHIN GROUP (ORDER BY delivered_at - submitted_at)` over requests submitted in the range
- `top_tasks_by_good_episodes`: `WHERE quality = 'good' … GROUP BY task_name ORDER BY count DESC LIMIT 5`

Each is one SQL statement; Python only serialises the result (a test asserts the query count).

### At 5 million episodes

Measured on a laptop (Docker Postgres 16, default settings) after importing 1,000,000 generated episodes
(`seed/generate_episodes.py 1000000`) on top of the seed data:

| Query | 30-day window (82k rows) | 12-month window (1M rows) |
|---|---|---|
| episodes per day per robot | 29 ms — index-only scan on `(recorded_at, robot_id)` | 1.1 s — planner switches to a sequential scan + hash aggregate |
| top 5 tasks by good episodes | 23 ms | 140 ms (parallel aggregate) |
| requests by status + median | < 1 ms (small table) | < 1 ms |
| whole `/api/analytics` call | 0.35 s | 0.41 s |

Importing the 1,000,000 rows took 112 s (≈ 9k rows/s) through the same importer, in one transaction.

Both episode queries use the `(recorded_at, robot_id)` / `(quality, task_name, recorded_at)` indexes, so cost
is proportional to the rows **in the date range**, not the table size. At 5M rows a typical 30-day window
(~400k rows) stays well under a second; a whole-year window becomes a multi-second scan, and the
per-day/per-robot result set itself grows (365 × robots rows). The change at that point is a daily rollup
table or materialized view (`day, robot_id, task_name, quality, count`) refreshed after each import, and serving
the dashboard from it. The request-fulfilment query is on the much smaller `requests` table and is unaffected.
The importer would also need to switch to `COPY` into a staging table (see NOTES.md).

## Development

`make` with no target lists everything. Each target wraps a plain `docker compose` / `manage.py` / `npm` command (make prints what it runs), so nothing depends on make.

| Command | What it does |
|---|---|
| `make server` | Backend locally with auto-reload on :8000 (creates the venv and `.env`, starts Postgres, migrates). `PORT=8001` to change |
| `make web` | Frontend dev server on :5173, proxying `/api` and `/health` to :8000 |
| `make seed` | Create/update the seed accounts locally |
| `make import FILE=…` | Run the CSV importer locally |
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
  episodes/   Episode + ImportRun models, importer.py, import_episodes command, list endpoints
  dataset_requests/  DatasetRequest, StatusEvent, Assignment; services.py (all rules); views
  analytics/  queries.py (SQL aggregates), view
  core/       /health view, request-logging middleware
  tests/
frontend/
  src/        App.tsx (routes + nav), LoginPage, RequestsPage, RequestDetailPage, EpisodesPage, api.ts, auth.tsx
  nginx.conf  serves the build, proxies /api and /health to the api container
seed/         users.json, episodes.csv (messy), generate_episodes.py
```
