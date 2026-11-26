# Known limitations

This page is deliberately blunt. A feature that has not been run is not a
feature that is proven. Phase 9's acceptance report should be read together with
this list.

## Deployment and operations

- **Docker is not installed on this machine.** The Compose stack, Caddy config,
  and Dockerfiles are committed but have never been built or started here. Native
  Windows is the only verified deployment.
- **GitHub Actions has never run.** The CI workflow is syntactically committed;
  its first real run may surface image, cache, or service differences.
- **One API and one worker** are the supported topology. The job queue can
  technically support more workers, but a single local GPU and the current
  heartbeat/model-residency assumptions are not tested beyond one.
- **Rate limits are in-process.** Restarting the API clears the registration,
  login, and request buckets. They are a local abuse control, not a distributed
  edge limiter.
- **No automatic job cleanup.** Finished jobs older than 30 days are deleted only
  when an account presses **Clean up expired** on Diagnostics. Trash purge runs at
  API startup and on demand.
- **Backups are local and unencrypted by default.** The scripts and restore drill
  exist, but there is no offsite replication, key management, or immutable
  retention in this repository.
- **The HNSW migration blocks writes while it builds.** At 100k rows the index
  build took about 112 seconds; a larger production table needs a quiet window.
  There is no concurrent/online index path.
- **pgvector 0.8 or newer is required** for relaxed iterative HNSW scans. The
  Compose image tag is not pinned to a patch version.

## Scale evidence

- **The 1.1M-word corpus is synthetic.** It is generated for structure, size,
  planted contradictions, near-miss quotes, and deterministic vectors. It is not
  JJK or One Piece text and cannot prove semantic extraction quality on either.
- **The default vectors are meaningless by construction.** They make latency
  measurements honest, but they are unit vectors, not embeddings. Retrieval
  relevance must be measured with `--embedding-mode ollama` or another real
  embedding model.
- **No full extraction-quality score at 1.1M words.** The fixture plants 100
  contradictions and 100 near-misses, but Phase 9 did not run exhaustive
  extraction and judge every result. Coverage/latency are measured; literary
  quality is not.
- **The HNSW recall number is a benchmark, not a guarantee.** Recall 1.0 at 100k
  rows came from a clustered synthetic distribution with 30 neighbors. A
  different corpus, dimensionality, or `ef_search` can do worse.
- **The full local-embedding import was extrapolated, not measured.** A 10-chapter
  `nomic-embed-text` sample ran at 11.8 chunks/s; the full 6,600-chunk run was
  estimated at about nine minutes. The synthetic import itself is measured.
- **Search latency is embedding-bound.** At 6,600 chunks the hybrid p50 was
  135.5 ms, of which about 69.6 ms was the query embedding call. A cold first
  search was about 4.7 seconds. Faster hardware or a smaller model moves this; the
  API code alone does not.
- **The database is 92 MB at 1.1M words.** That is a useful local scale test, not
  a claim about 10M words, millions of chunks, or multi-user concurrency.

## Product and behavior

- **No collaboration, sharing, teams, or roles.** One owner per story.
- **Lazy canon extraction is intentional.** Opening a large imported story does
  not scan every chapter. Older arcs remain unextracted until the writer asks;
  coverage is visible rather than silently backfilled.
- **HNSW is approximate.** The app favors recall with `ef_search=400` and
  iterative scans, at the cost of memory and index size. The index roughly
  doubles chunk storage at 100k rows.
- **Search is not a general web/search engine.** It combines story-scoped vector,
  lexical, and name signals; typo tolerance and ranking quality are bounded by
  those components.
- **The editor is a rich text/CodeMirror surface, not a Word clone.** Complex
  tables, tracked changes, and collaborative cursors are out of scope.
- **Exports depend on the local Chrome/Edge print engine for PDF page numbers.**
  The PDF is valid without them, but older engines may omit the numbers.
- **Browser QA is Chromium-only.** Firefox and Safari are not covered by the
  Playwright suites.
- **No native mobile app.** The web UI is responsive, not a separate mobile
  client.
- **The app does not encrypt data at rest.** Disk encryption and OS access
  control are the operator's responsibility.

## Verification gaps

- **The longest soak is 30 minutes, not 24 hours.** That run mixed searches,
  story/chapter reads, and repeated saves with worker reindexing. The measured
  duration is in the Phase 9 acceptance report; do not describe it as a 24-hour
  soak.
- **No real multi-user load test.** Tests exercise ownership isolation, not many
  writers hitting the same database concurrently.
- **No disaster-recovery exercise from a second machine.** The restore drill is
  local and uses a throwaway database.
- **No formal accessibility audit** beyond the Phase 7 keyboard/focus/contrast
  pass and Chromium checks.
- **The scale API measurements are single-run samples** with unique query
  nonces, not a statistically rigorous benchmark. They are evidence of magnitude,
  not a service-level guarantee.