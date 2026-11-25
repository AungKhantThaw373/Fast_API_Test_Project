# Data retention and deletion

Stillroom keeps one PostgreSQL database and stores uploaded drafts in it.
This page says what stays, for how long, and what leaves when you ask.

## Your account

| Data | Retention |
|---|---|
| Username, email, password hash, account dates | Until you delete the account |
| Login failures and successes | 30 days, pruned at the next successful sign-in |
| Active sessions | Until revoked or expired (30 minutes by default) |
| Revoked sessions | 30 days after revocation |
| Password reset tokens | 30 days after expiry; using one consumes it immediately |
| Audit events (provider change, trashed story, export, password change, merge) | Until you delete the account; visible in **Settings → Activity** |

## Stories and drafts

| Data | Retention |
|---|---|
| Stories, chapters, wiki entries, arcs, threads, facts, relationships | Until you delete them |
| Trashed stories and chapters | 30 days, then permanently removed by the purge job |
| Chapter revisions | All revisions younger than 48 hours; one per hour up to 7 days; one per day up to 90 days; checkpoints and restore points are kept until the chapter is deleted |
| Draft files (PDF, DOCX, ODT, DOC, RTF, text) | Until you delete the file or account; counted against the 500-file / 2 GiB account quota |
| JSON story backups | Only the file you download; Stillroom keeps no second copy |
| AI usage ledger | Kept with the account so monthly budgets stay correct; deleted with the account |

## Deletion

- **Trash** removes a story or chapter from the library at once. It remains recoverable for 30 days, then a durable job deletes it permanently. Permanently deleting from the trash skips the wait.
- **Delete account** in **Settings** verifies your password and requires your username to be typed exactly. It deletes the account row and every story, chapter, wiki record, draft file, session, setting, AI ledger row, and audit event owned by that account. It writes one anonymised `account_deleted` audit record with no email, user id, or username, then clears the sign-in cookies. The action cannot be undone.
- A deletion is immediate in the live database. Point-in-time database backups made before the deletion may still contain the data until the backup rotation expires; that is true of any backup system. Keep the backup directory on a machine you control and protect it like the database itself.

## Backups

`scripts/backup.sh` writes a `pg_dump` of the database to `backups/`. A backup is a full copy of every account, so protect it with filesystem permissions and a disk you trust. Restore steps live in `Docs/backups.md`.

## Exports

**Settings → Data → Export all my data** builds a zip on demand and streams it to you. It contains:

- `stillroom-export.json`: account details, every story with chapters and revisions, wiki records, arcs, threads, events, canon exceptions, and draft metadata.
- `stories/NN-title.md`: a readable Markdown manuscript per story.
- `drafts/…`: your original uploaded files, byte for byte.
- `README.txt`: a short description of the archive.

Provider API keys are **never** included. The export is generated in memory for one request and is not stored on the server.

## Logs

The API log includes request ids, timings, and route names. Password-reset links are written to the log only when no SMTP host is configured (the local development default); the raw token is never stored in the database, only its SHA-256 hash. Audit events never include chapter prose.