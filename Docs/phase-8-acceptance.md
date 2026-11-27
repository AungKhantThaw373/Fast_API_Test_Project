# Phase 8 acceptance — security and operations

Goal: make Stillroom safe for daily use on a trusted home network, safe enough to expose through a private tunnel, and recoverable from its own backups.

Tagged `phase-8-complete`. This page maps the manual's acceptance list to the code, tests, and checks that actually ran. Where something is documented but was not executable on this machine, it says so.

## P8-1 — Rate limiting and lockout

- `backend/app/rate_limits.py` implements an in-process token bucket. Login is limited to 5 failures / 15 minutes per IP and per account, registration to 3 / hour per IP, AI scans to 10 / hour per user, uploads to 20 / hour per user, and password resets to 5 / hour.
- `login_attempts` (migration `b8d1c4e7f2a9`) records IP, email, success, and time. Five failures lock the account even when the source address changes. A successful sign-in deletes the failures for that email and IP, resets the IP bucket, and leaves a successful audit row.
- Security rows older than 30 days are pruned during the next successful sign-in.
- `backend/tests/test_security_limits.py` covers the 6th attempt, the lockout window, IP separation, and a success clearing the count.

## P8-2 — CSRF and origin checks

- `backend/app/security_middleware.py` rejects unsafe requests whose `Origin` is not a configured frontend origin or the API's own origin, rejects `Sec-Fetch-Site: cross-site`, and requires `X-CSRF-Token` to equal the readable `csrf` cookie (double submit).
- Safe requests without a token receive one. The auth cookie stays HttpOnly; only the CSRF cookie is readable by the app.
- `frontend/lib/api.ts` sends the header on every write. The Playwright suites use `frontend/scripts/qa-csrf.mjs` for their direct API calls.
- `backend/tests/test_security_csrf.py` covers missing, mismatched, cross-origin, and valid-token requests.

## P8-3 — SSRF protection

- `backend/app/services/url_safety.py` allows only `http`/`https`, rejects credentials, query strings, fragments, and every resolved private, loopback, link-local, reserved, multicast, or unspecified address. `provider_http_client()` never follows redirects.
- Local Ollama is the one deliberate exception: loopback and LAN addresses are accepted for the `ollama` provider so the bundled offline default keeps working. Link-local metadata addresses remain blocked there too.
- `PROVIDER_HOST_ALLOWLIST` can narrow production hosts further.
- Residual risk: DNS rebinding. The check resolves before the request and the HTTP client resolves again, so a hostile DNS server can change the answer between the two. This is documented rather than hidden; a pinning transport is the next step if the app is ever exposed to untrusted provider URLs.
- `backend/tests/test_url_safety.py` covers loopback, metadata, private ranges, credentials, queries, redirects, and the Ollama exception.

## P8-4 — Security headers and cookies

- `backend/app/security_headers.py` sets `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `X-Frame-Options: DENY`, a strict production CSP, and HSTS only when the request is HTTPS. The API CSP is applied in production only so FastAPI docs remain usable in development.
- Auth cookies are `__Host-token` in production HTTPS (`Secure`, `SameSite=Lax`, `Path=/`, no `Domain`). Development and tests use `token` because `__Host-` requires HTTPS.
- The Next app sends its own headers. Its CSP is report-only until a nonce can be generated per request; the API's CSP and frame denial are enforced. This is an honest gap, not a claim that the Next CSP blocks scripts today.
- `backend/tests/test_security_headers.py` covers production headers, HSTS over HTTPS only, cookie flags, and the development exception.

## P8-5 — Upload safety

> Retired after acceptance: the `/editing` page and upload API were removed. Existing uploads remain in PostgreSQL and account export; the checks below describe the historical implementation.

- Signatures, not extensions, are checked for PDF, DOCX, ODT, DOC, RTF, and text in `editing_routes.py`; the 25 MiB file limit and the 500-file / 2 GiB account quota are enforced server-side.
- Downloads use `Content-Disposition: attachment`; inline previews are limited to PDF and plain text and carry `Content-Security-Policy: sandbox; default-src 'none'; frame-ancestors 'self'`.
- The preview iframe in the editing desk uses `sandbox="allow-same-origin"` with `referrerPolicy="no-referrer"`. User HTML is never rendered.
- A separate `files.` origin is not implemented. The sandboxed document with its own CSP is the mitigation used here; `Docs/deployment.md` explains where a separate hostname would go if the app is exposed beyond a trusted network.
- `backend/tests/test_upload_safety.py` covers signatures, quota, file count, and download headers.

## P8-6 — Sessions and accounts

- JWTs carry `iat`, `exp`, `jti`, `iss`, `aud`, and the user's `token_version`. `User.token_version` is incremented on password change, password reset, sign-out-everywhere, and account deletion; `get_current_auth` also requires a live, non-revoked `AuthSession`.
- Password reset uses a one-time hashed token with a 30-minute expiry. Local mode prints the link to the API log; SMTP settings send it when configured.
- `GET /sessions`, `DELETE /sessions/{id}`, and `POST /sessions/revoke-all` back the Settings session list. The list shows device, address, created-at, and last-seen.
- `backend/tests/test_account_sessions.py` covers session listing/revocation, token version invalidation, single-use and expired reset tokens, and password changes.

## P8-7 — Quotas, audit, and data control

- Draft quota: 500 files / 2 GiB per account, with per-file 25 MiB.
- Stories return `chapter_warning_at`; the dashboard warns when a story crosses the configured chapter count but does not block.
- `audit_events` (migration `e5a9c3d7b2f4`) records trashing and permanent deletes, merges and unmerges, story/chapter exports and backups, restores, provider changes and resets, password changes/resets, data export, and account deletion. Rows store identifiers, a short detail, address, and time, never prose.
- `GET /account/audit` feeds **Settings → Activity**. `GET /account/export` builds a ZIP in memory with JSON, Markdown manuscripts, and original drafts; provider API keys are excluded. `DELETE /account` requires the typed username and password, removes owned data, writes one anonymised `account_deleted` row, and clears cookies.
- `Docs/data-retention.md` documents retention, deletion, exports, and the backup caveat.
- `backend/tests/test_data_control.py` covers export contents, the audit list, typed deletion, and anonymised deletion.

## P8-8 — Observability

- Request IDs and timings were already in place. `backend/app/db.py` now logs statements slower than `SLOW_QUERY_MS` (default 500 ms) at WARNING with duration and a whitespace-collapsed, 400-character statement, never parameters.
- `GET /system/diagnostics` returns database size and health, job counts by status (`queued`, `running`, `succeeded`, `failed`, `dead`), the newest `stillroom-*.dump`, Ollama/protocol status, schema revision, and 30-day AI usage grouped by purpose.
- `frontend/app/diagnostics/page.tsx` renders those cards with a refresh action. It is the owner's page; the API still requires authentication.
- Error tracking is optional in the manual and was not added. The slow-query log, request IDs, and job counts are the observability actually shipped.
- `backend/tests/test_diagnostics.py` covers the response fields, newest backup selection, unauthenticated access, and the no-parameters slow-query log.

## P8-9 — Supply chain and deployment

- CI runs `uv run --with pip-audit pip-audit`, `npm audit --audit-level=high`, and a gitleaks job. Dependabot checks pip, npm, and GitHub Actions weekly; `.gitleaks.toml` allowlists CI/test placeholders.
- The dependency audit found 53 Python advisories across 9 packages and 6 npm advisories. `uv lock --upgrade` + `uv sync` and `next@16.4.6`, `eslint-config-next@16.4.6`, `vitest@5.1.2`, `@types/node@24` cleared them; both auditors now report zero.
- `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, and `deploy/Caddyfile` define the API, worker, PostgreSQL/pgvector database, production Next server, and an optional Caddy TLS profile. The database port is not published; the web port binds to `127.0.0.1` by default.
- **Docker is not installed on this machine.** The Compose stack and both Dockerfiles have not been built or run. Their YAML and Dockerfile syntax were checked, and this limitation is written in `Docs/deployment.md` rather than presented as a verified deployment.
- `Docs/deployment.md` covers Compose, Caddy, Tailscale, TLS, environment, operations, backup, and restore. `Docs/backups.md` and `scripts/verify-backup.sh` describe and exercise the restore drill.
- Restore drill on 2026-11-25: `scripts/verify-backup.sh backups/stillroom-2026-11-25-1511.dump` restored into a throwaway `stillroom_verify_*` database, read Alembic revision `e5a9c3d7b2f4`, and counted 121 users / 121 stories / 228 chapters / 1,230 entities before dropping it.

## Verification actually run

```text
backend:  uv run pytest -q                 -> 247 passed
          uv run ruff check .              -> clean
          uv run pyright app               -> clean
          pip-audit                        -> no vulnerabilities
frontend: npx tsc --noEmit                 -> clean
          npm run lint -- --quiet          -> clean
          npm run test                     -> 47 passed
          npm run build                    -> production build
          npm audit --audit-level=high     -> 0 vulnerabilities
browser:  npm run qa:phase7                -> 8 suites, 85 checks
          npm run qa:phase8                -> 13 checks
```

The Phase 7 browser suite now shares one QA account and login across its eight suites because registration is deliberately limited to three per hour and login to five per fifteen minutes. This is the product's security behavior, not a test workaround.

## Deliberate omissions and follow-ups

- Docker/Compose is unexecuted here. Run it on a machine with Docker before relying on it.
- Next's CSP is report-only; the backend CSP is enforced. A nonce-based Next CSP is the next step.
- Upload previews remain same-origin in development. Use a separate files hostname when exposing the app.
- DNS rebinding remains possible for provider URLs; pinning the resolved address is the next hardening step.
- GlitchTip/Sentry-style error tracking was not added.
- Audit retention follows the account, and deletion removes prior events while leaving one anonymised record. The manual does not require a longer-lived tamper-evident log.
- One task normally gets one commit. Phase 8 was implemented in an interrupted working tree before the commits were split by task; the commits are task-shaped, but they are not independently bisectable. The verified artifact is the final tree at `phase-8-complete`.

## Post-release fix: expired-session redirect

- A 401 from a protected API call now sends the writer to
  `/login?next=<current-page>`, once, including calls made outside React Query
  and file downloads. `/token`, `/register`, and the password-reset endpoints are
  excluded so invalid credentials remain form errors.
- The login page validates `next` as a same-origin path and returns there after
  signing in; auth pages and protocol-relative/external URLs fall back to
  `/dashboard`.
- The Phase 8 browser suite now revokes the current session and checks both the
  redirect and the return to `/settings`: **15/15**. Five vitest cases cover the
  helper.