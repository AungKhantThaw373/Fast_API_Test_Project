# Background worker

Long AI work — chapter reindexing and Story Bible extraction — does not run inside
the API process. The API writes a row to `jobs`; `app/worker.py` claims it from
Postgres and runs it. A crash loses no work and the API stays responsive.

## Run it

Two processes, locally:

```bash
make dev-backend     # uvicorn on :8000
make worker          # uv run python -m app.worker
```

`make worker-once` drains only jobs that are already due (the autosave debounce
leaves a job queued for 2.5 s), then exits. It is what CI and the tests use.

Run **one** worker. `MAX_CONCURRENT_JOBS` is 1 because a 6 GB GPU cannot hold two
models at once: a chapter reindex and a Bible scan would evict each other.
Scaling out means more VRAM, not more worker processes.

## Lifecycle

| Status | Meaning |
|---|---|
| `queued` | Waiting for `run_at`. Duplicate enqueues push `run_at` forward. |
| `running` | Claimed by a worker; `locked_at` is refreshed every 15 s. |
| `succeeded` | Finished. `progress` holds `{"stage": "done"}`. |
| `failed` | Reserved for a non-retryable handler outcome. |
| `dead` | Attempts exhausted. `last_error` explains why. |

Behaviour worth knowing:

- **Claiming** uses `FOR UPDATE SKIP LOCKED`, so two workers never take the same
  row. `uq_jobs_active_dedupe` allows one active job per `(type, dedupe_key)`.
- **Retries** back off 5 s → 15 s → 45 s, then the job is `dead`.
- **Superseded work** (the chapter changed mid-run) is requeued after 5 s instead
  of counting as a failure; the chapter stays `pending` and the newer text wins.
- **Crash recovery**: on startup a worker resets `running` jobs whose lock is
  older than 15 minutes back to `queued`.
- **Signals**: `SIGINT`/`SIGTERM` stop claiming, finish the job in hand, and
  release the lock.
- **Heartbeat**: `worker_heartbeats` is upserted every 15 s. `/system/status`
  reports `worker: "running"` while the heartbeat is under 60 s old, and
  `/ready` uses the same check.

## Endpoints

- `GET /jobs/{id}` — status, attempts, progress, `last_error`. Owner only; another
  user gets 404.
- `GET /system/status` — `queued_jobs`, `running_jobs`, `dead_jobs`, `worker`.

## Statement timeout

Worker connections use 5 minutes (`STATEMENT_TIMEOUT_MS`, set at the top of
`app/worker.py` before `app.db` is imported); API connections use 15 s. A bulk
reindex or a slow provider call is legitimately long, a request is not.

## Inspecting the queue

```sql
SELECT type, status, count(*) FROM jobs GROUP BY 1, 2 ORDER BY 1, 2;
SELECT id, type, attempts, last_error FROM jobs WHERE status = 'dead';
```

Recovering by hand: `UPDATE jobs SET status='queued', run_at=now(), attempts=0
WHERE id = '<id>';`. The worker picks it up on the next poll.
