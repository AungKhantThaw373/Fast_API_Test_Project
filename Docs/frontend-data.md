# Frontend data layer

One server-state layer for every screen: TanStack Query, one client, explicit
invalidation. The rule is simple — a mutation names the queries it invalidates,
and nothing invalidates everything.

## Where things live

| File | Purpose |
|---|---|
| `lib/query-client.ts` | `QueryClient` factory: 30 s stale time, 5 min cache, 1 query retry, 0 mutation retries, toast + one-time 401 redirect |
| `app/providers.tsx` | client boundary that installs the provider and the toaster |
| `lib/query-keys.ts` | the key factory; never build keys by hand |
| `lib/api.ts` | typed fetchers; every call goes through `request()` which owns auth errors and 409 conflicts |
| `lib/api-types.ts` | generated from `/openapi.json` (`npm run gen:api`, backend must be running) |

## Keys

```ts
qk.entity(id)                   ["entity", id]
qk.entityFacts(id)              ["entity", id, "facts"]
qk.entities(storyId, filters)   ["entities", storyId, filters]
qk.entityList(storyId)          ["entities", storyId]              // prefix of every filtered list
qk.inbox(storyId)               ["inbox", storyId]
```

Prefix invalidation is deliberate: `qk.entityList(storyId)` refreshes every
filtered entity list for that story, and `qk.entity(id)` refreshes the detail
page without touching lists.

## Invalidation rules

| Mutation | Invalidate |
|---|---|
| chapter save | `chapter(id)`, `chapters(storyId)`, `story(storyId)` |
| entity create / edit / archive / merge | `entity(id)`, `entity(targetId)` on merge, `entityList(storyId)`, `inbox(storyId)` |
| alias add / remove | `entity(id)` |
| fact create / edit / accept / reject / delete | `entityFacts(entityId)`, `entity(entityId)`, `inbox(storyId)` |
| relationship add / remove | `entityRelationships(entityId)` |
| thread create / update / delete | `threads(storyId)`, `inbox(storyId)`, and `entity(entityId)` when linked |
| inbox decision (accept / reject) | `inbox(storyId)`, `entityFacts(entityId)`, `entity(entityId)` |
| scan completes | `scan(chapterId)`, `inbox(storyId)` |
| exception add / remove | `exceptions(storyId)` |

## Optimistic updates

- Decisions (accept / reject in the inbox, resolve a thread) update the cached
  list immediately and roll back on error.
- Entity edits and merges are ordinary mutations: invalidate after success.
  They are rare, and a wrong optimistic merge is worse than a 200 ms wait.

## What the studio keeps outside the cache

The chapter editor is not a query. Its local state is driven by the save-state
machine (`lib/save-state.ts`) and the IndexedDB draft buffer, because losing a
keystroke to a cache refetch is unacceptable. Reads that the editor does not own
(story, chapter list, findings, inbox counts) go through the query cache.

## Phase 4 additions

| Module | What it owns |
|---|---|
| `lib/query-keys.ts` `arcs(storyId)` | arc list per story, invalidated after create/rename/assign |
| `components/wiki/use-wiki.ts` `useChapters`, `useArcs` | read-only hooks for the palette, the threads page, and the arc filter |
| `components/wiki/threads-page.tsx` | `threads(storyId)`; resolving also invalidates `inbox(storyId)` |
| `components/wiki/inbox-page.tsx` | `inbox(storyId)` for every kind, plus local keys `[…, "rules"]` and `[…, "rules", "preview"]` under the same prefix so one invalidation clears all three |
| `components/wiki/arc-page.tsx` | `entities(storyId, { arc_id })` under its own key suffix, and `arcs(storyId)` for the header |
| `components/wiki/saved-views.tsx` | localStorage only — no query, no server state |
| `components/command-palette.tsx` | `api.searchEntities` on a 200 ms debounce; results are component state, not cache (they are ephemeral by design) |

Inbox decisions are the one place where an optimistic update matters most: the
cached list drops the decided ids immediately and restores the previous list if
the request fails, because a review list that lags behind the keyboard is
unusable. Everything else follows the invalidate-after-success rule.

The desk panel's width, the collapsed state, and the saved wiki views are all
local UI state persisted in `localStorage` (`stillroom:pane-width`,
`stillroom:saved-views`). Nothing about them belongs in the query cache.
