# Notes

> Working draft. Final sections required by the brief: Design · Left out / next · Something that went wrong · Security · Scale · AI tooling.

## Decisions log (kept while building)

- **Custom `User` from the first migration** (`AbstractBaseUser`), email as login, a single `role` field (`client` / `operator` / `admin`). Django's groups/permissions are not used: the role model in the brief is small and fixed, and one field is easier to reason about and test.
- **Emails stored lowercased**, so uniqueness and login are case-insensitive.
- **Django admin is not installed.** It would be a second write path that bypasses the request workflow rules and audit trail.
- **`/health` is unauthenticated** (a health check that requires a session is useless to Docker / load balancers). It runs `SELECT 1` and returns 503 if the DB is unreachable. It exposes no data.
- **Request logging** is a middleware placed first in the stack, so `duration_ms` covers all other middleware. Gunicorn's and runserver's own access logs are disabled to keep exactly one line per request. 4xx lines are logged at `warning`, 5xx at `error`.
- **Frontend is served same-origin** (nginx proxies `/api` to Django), so session cookies and Django's CSRF protection work without any cross-origin setup.
- **Postgres published on `127.0.0.1:55432`**, not 5432, to avoid clashing with a locally installed Postgres (it happened on my machine).
- **Secrets**: `DJANGO_SECRET_KEY` is required unless `DJANGO_DEBUG=1`; the value in `docker-compose.yml` is a dev placeholder, not a secret.
