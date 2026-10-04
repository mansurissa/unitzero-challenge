# Notes

## 1. Design

### Data model

```
User (role: client | operator | admin)
  │
  └──< DatasetRequest ──< StatusEvent        who moved it, from what, to what, when, note
            │
            └──< Assignment >── Episode       one row per episode attached to a request;
                                               removing sets unassigned_at, the row stays
ImportRun                                      one row per CSV import, with the full report
```

- **User**: custom model from the first migration. Email is the login. One `role` column decides what a user can do. I did not use Django's groups and permissions: the brief has three fixed roles, and one column is easier to read, test and show in the UI.
- **Episode**: keyed by the recording system's `episode_id` (unique). Three indexes, each for a known query: `(recorded_at, robot_id)` for episodes per day per robot, `(quality, task_name, recorded_at)` for top tasks and the operator's filtered list, `task_name` for the task filter alone.
- **DatasetRequest**: has `status`, `submitted_at` and `delivered_at` on the row so lists and analytics are cheap. The real history is in **StatusEvent**, which is append-only.
- **Assignment**: the rule "an episode is in at most one request at a time" is a **partial unique index** in PostgreSQL (`UNIQUE (episode) WHERE unassigned_at IS NULL`). The database enforces it even if two operators click at the same moment. Unassigning does not delete; it sets `unassigned_at`, so we can always see what was delivered before a rework.

### Where state lives

Everything is in PostgreSQL. The API is stateless except for Django's DB-backed session. All business rules are in one file, `dataset_requests/services.py`: the transition table, who may do what, the row lock, the "enough episodes" check, and the event written for every change. Views only validate input and call these functions. The CSV importer is the same idea: one function, used by both the command and the start-up script.

### The three hardest decisions

1. **What to do when a CSV row disagrees with what is already stored.** The seed file has `EP-00011` as both `bad` and `good`. If I overwrite, an episode that is already assigned and delivered could silently become `bad`. I chose: never overwrite, report the row as `conflicts_with_existing`, and let a person look. Re-running the same file is then naturally safe: identical rows are `already_imported`. If the recording system is ever declared the single source of truth, "last write wins" is a one-line change (`bulk_create(update_conflicts=True)`).

2. **When assignments may change, and what happens on rejection.** The brief only says delivery needs enough episodes. I decided episodes can be assigned or removed **only while the request is `in_progress`**: before that nobody is working on it, and after delivery the client is reviewing a fixed set. When a client rejects and the operator restarts work, the assignments are **kept**. The client usually complains about one or two clips, not all of them; clearing everything would throw away work.

3. **Sessions instead of JWT.** The frontend is served from the same origin as the API (nginx proxies `/api`), so Django's session and CSRF protection work as designed. The cookie is `HttpOnly`, logout and deactivation take effect immediately, and nothing is stored in the browser that can leak. A JWT would only help third-party API clients, which this system does not have.

Smaller decisions: only clients create requests; a client asking for another client's request gets **404, not 403**, so ids leak nothing; `delivered_at` records the **first** delivery so rework does not reset the fulfilment metric; naive timestamps in the CSV are treated as UTC; `task_name` is lower-cased and whitespace-collapsed so "Pick Cup" and "pick cup" are the same task in analytics; durations must be whole seconds between 1 and 3600 (`45.5`, `N/A`, `-5`, `999999` are reported, not guessed); a missing operator name is a warning, not a rejection, because nothing depends on it.

## 2. What I left out, and what I would do with two more days

Left out on purpose: editing or cancelling a request; an admin screen for users (the API exists and is tested); the CSV upload endpoint (the command satisfies the brief, and it runs on every container start); pagination controls on the requests list (first 50); login rate limiting; the stretch item.

With two more days, in this order:

1. **Real-time updates (the stretch I would pick)** with Server-Sent Events, not WebSockets: the need is one-way ("something changed, refetch"), Postgres `LISTEN/NOTIFY` gives cross-process fan-out without Redis, and `EventSource` reconnects by itself. About 80 lines; WebSockets via Channels would mean an extra Redis container and more code for a problem we do not have.
2. `COPY`-based import into a staging table for multi-million-row files (see §5).
3. Cursor pagination for the episode list.
4. A CI workflow (Postgres service, `pytest`, `makemigrations --check`, frontend build) and a Playwright smoke test of the two UI flows.
5. A password-change flow and login throttling.

## 3. Something that went wrong

The first time I ran the tests locally, Django could not connect to the database: `password authentication failed for user "requestdesk"`, even though the compose file set exactly that user and password and the container was healthy. The password was right; the _server_ was wrong. My machine already had a PostgreSQL running on port 5432 (a leftover from another project), so the connection went to it instead of the container. `lsof -i :5432` showed a non-Docker `postgres` process. Fix: publish the compose database on `127.0.0.1:55432` instead, which also protects anyone who clones the repo and has the same setup. It is written in the README.

A smaller one: my first expected number for the seed import was 173 inserted; the importer said 172. I assumed the importer was wrong. Instead I printed its per-line report and saw I had missed that `EP-00030` appears twice too. The report format exists exactly so this kind of question can be answered without reading code, so the failing test was doing its job.

## 4. Security

- **Passwords** are hashed with Argon2id. The seed command calls `set_password`, so the plain-text values in `users.json` never reach the database. Minimum length is enforced when an admin creates a user.
- **Sessions**: DB-backed, cookie `HttpOnly` + `SameSite=Lax` (`Secure` behind HTTPS via `DJANGO_SECURE_COOKIES=1`). Every write needs Django's CSRF token. A deactivated user is refused on their next request, not just at the next login.
- **Authorization is enforced twice**: DRF permission classes on every endpoint (the default is "logged in", only `/health`, login and the CSRF endpoint are open), and again inside the service functions, which take the acting user and check role and ownership themselves. Clients' querysets are filtered at the ORM level, so no route can reach another client's request.
- **Input**: serializers validate every write; the CSV is parsed as text with the standard `csv` module and every field is checked before it touches the database; `CHECK` and unique constraints in PostgreSQL are the backstop. React escapes rendered strings, so a crafted `task_name` in a CSV cannot inject markup.
- **Secrets**: `DJANGO_SECRET_KEY` is required unless `DJANGO_DEBUG=1`; the compose file holds dev placeholders only.

The two vulnerabilities I would worry about most: **(a) broken access control between clients.** Multi-tenant data is one forgotten `filter(client=user)` away from a leak as more endpoints are added. That is why the rules sit in the service layer and why the authorization matrix is a parametrised test. **(b) The import path**, the one place bulk untrusted data enters: a bad or malicious export could flood the table or exhaust memory. Today it is operator-only, validated field by field and audited per run; it still needs a size limit and to run outside the request cycle if it ever becomes an upload.

## 5. Scale

**10× users**: nothing structural breaks. Gunicorn's three sync workers would saturate before PostgreSQL does; the fix is more workers or replicas behind nginx, and a connection pooler. The row lock in `transition()` is per request, so contention stays local.

**100× episodes, and 5 million**:

1. **The importer** reads the whole file into memory and inserts in one transaction. Fine for a daily export, not for a 5M-row backfill. Change: stream the file with `COPY` into an unlogged staging table, validate in SQL, then `INSERT … SELECT … ON CONFLICT DO NOTHING`.
2. **Analytics**: the three queries are single `GROUP BY` statements on indexed columns, so cost follows the rows in the date range, not the table size. I measured them after importing 1,000,000 generated episodes: a 30-day window answers in about 30 ms; a full-year window takes about 1.1 s because the planner switches to a sequential scan. At 5M rows a wide window needs a daily rollup table (`day, robot_id, task_name, quality, count`) refreshed after each import. Numbers are in the README.
3. **The episode list** uses page-number pagination, which runs `COUNT(*)` on every page. Switch to cursor pagination on `(recorded_at, id)`.
4. The "which request holds this episode" column is a correlated subquery backed by the partial index, so it stays proportional to the page size.

## 6. AI tooling

I used Claude Code to compare stacks and find different alternatives. I also used it to debug but the ideas are mine.
