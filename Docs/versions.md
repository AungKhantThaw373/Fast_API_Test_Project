# Versions

Recorded 2026-11-24 on the development machine.

| Component | Version |
|---|---|
| Python (project, via uv) | 3.12.13 |
| uv | 0.11.7 |
| Node | 24.14.1 |
| npm | 11.11.0 |
| PostgreSQL | 18.7 (native Windows install, no Docker) |
| pgvector | 0.8.7 |
| pg_trgm | 1.6 |
| Ollama | 0.30.8 |
| Embedding model | `nomic-embed-text` (768 dimensions) |
| Next.js | 16.2.4 |
| React | 19.2.4 |
| Tailwind CSS | 4.x |

CI runs the backend against `pgvector/pgvector:pg16` and the frontend on Node 20.
The app must keep working on both PostgreSQL 16 and 18: no version-specific SQL.

Package managers: **npm** for the frontend (single `package-lock.json`; the old
`pnpm-lock.yaml` was removed), **uv** for the backend (`uv.lock` is committed).
