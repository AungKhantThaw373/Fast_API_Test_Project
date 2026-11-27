# Privacy and data handling

Stillroom is designed as a private, local-first writing tool, but privacy is a
deployment property, not a promise the code can make by itself. This page states
what the application stores, what leaves the machine, and what the operator must
protect.

## Where the data lives

| Data | Location |
|---|---|
| Accounts, stories, chapters, revisions, chunks, embeddings, knowledge model, jobs | PostgreSQL on the host (default `127.0.0.1:5432`) |
| Auth cookie | Browser, HttpOnly; `__Host-` prefix when served over HTTPS |
| Unsaved editor buffer | Browser IndexedDB for the current origin |
| Saved wiki views, theme, UI preferences | Browser localStorage |
| Backups | `backups/` on disk, written by `scripts/backup.sh`; not encrypted by the script |
| Application logs | Local stdout/files; request id, path, status, timing, slow SQL shape |
| Audit trail | `audit_events` in PostgreSQL; account actions with IP and a user snapshot |

There is no application-level analytics SDK, advertising pixel, or telemetry
endpoint. Next.js dependencies include OpenTelemetry transitively, but the app
does not configure an exporter.

## What can leave the machine

Local Ollama is the default AI path. A request goes to a cloud provider only
when the writer configures a cloud provider/key (or the deployment supplies a
server key) and the action uses it. Depending on the action, the provider may
receive:

- the search query and retrieved prose chunks (ask-your-story, retrieval);
- chapter or scene text (Story Bible extraction, continuity, reindex embeddings);
- summaries, entity names, facts, and prior findings (continuity and recaps);
- the model name and generation settings.

The exact provider is visible in AI settings and the usage ledger. Choosing
`local` keeps prose on this machine. Cloud calls are recorded, not budget-gated;
a local-only story or one with external analysis disabled sends no prompt.

Provider-side retention and training are governed by that provider's terms,
not by Stillroom. Do not send text you are not allowed to send to that provider.

## Secrets and access

- Passwords are hashed with `pwdlib`'s recommended password hash; plaintext is
  never stored.
- Session JWTs are signed with `JWT_SECRET`; the `jti` points at a revocable
  `auth_sessions` row. Session cookies are HttpOnly and SameSite-protected.
- User AI keys are encrypted at rest with Fernet, derived from
  `AI_SETTINGS_ENCRYPTION_KEY` (or `JWT_SECRET` when unset). This is
  server-side encryption, not end-to-end encryption: the API process can decrypt
  a key while handling a request.
- `backend/.env` contains the database password, JWT secret, and possibly a
  server API key. It is git-ignored; restrict filesystem access and never paste
  it into an issue or log.
- CSRF uses a readable `csrf` cookie and the `X-CSRF-Token` header. The token is
  not a secret from the page; its purpose is to stop cross-site form posts.

The app does not encrypt the database at rest. Use BitLocker/FileVault or an
encrypted volume if the host disk is not trusted.

## Logs and diagnostics

Request logs record method, path, status, duration, and a request id. The slow
query logger deliberately records only the SQL shape and timing, not bound
parameter values. Application errors are logged with a stack trace; avoid
putting prose or keys into error messages.

`/system/diagnostics` and `/system/storage` are authenticated but expose
deployment-wide facts (database size, table sizes, AI provider status) alongside
account-scoped counts. Treat the diagnostics page as operator-only information.

## Retention and deletion

Trashed stories and chapters are kept for 30 days, then purged. Finished jobs
are eligible after 30 days and are removed by **Clean up expired**; that cleanup
is manual today. Revisions follow the tiered policy in
[data-retention.md](data-retention.md).

Account deletion is an explicit, typed action. It removes the account's active
data and sessions, but:

- backups made before deletion keep a copy until they age out of rotation;
- prior audit rows are deleted with the account; one anonymised
  `account_deleted` event remains, with no user id or email;
- provider-side copies are outside this application's control.

Export your data from Settings before deleting an account. The export includes
stories, chapters, knowledge, and settings, but not secrets such as plaintext API
keys.

## Browser storage

IndexedDB drafts are not encrypted by the app. Anyone with access to the browser
profile or the unlocked machine can read them. Use a separate OS/browser profile
for sensitive work, and clear site data after using a shared machine. The auth
cookie is HttpOnly, but the draft buffer is intentionally readable by the page so
it can recover from a crash.

## Threat model and limits

This is a single-user/local-first application, not a hardened multi-tenant
service. It has ownership checks, rate limits, CSRF, security headers, upload
validation, and revocable sessions, but it does not provide:

- per-story encryption or a customer-managed key;
- an administrator separation-of-duty model;
- protection from a compromised host, browser extension, or database superuser;
- guaranteed secure erasure from SSDs, backups, or provider systems;
- a warrant canary or jurisdiction-specific compliance certification.

For a shared or internet-facing deployment, put it behind TLS, restrict network
access, keep the database private, rotate secrets, and review
[limitations.md](limitations.md) before trusting it with unpublished work.