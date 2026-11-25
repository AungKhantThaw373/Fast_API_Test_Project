'use client';

import { useEffect, useMemo, useState } from 'react';

import { ApiRequestError, api, type Chapter, type StoryArc, type StorySearchHit, type StorySearchResponse, type WikiEntity } from '@/lib/api';

type Props = {
	storyId: string;
	chapters: Chapter[];
	arcs: StoryArc[];
	onOpen: (chapterId: string, line: number) => void;
};

const SCORE_LABEL: Record<string, string> = {
	vector: 'Vector',
	lexical: 'Full text',
	name: 'Name / alias',
};

function scoreRows(hit: StorySearchHit): Array<[string, number]> {
	return Object.entries(hit.scores)
		.filter(([, value]) => Number.isFinite(value) && value !== 0)
		.sort((left, right) => right[1] - left[1]);
}

export function StorySearch({ storyId, chapters, arcs, onOpen }: Props) {
	const [query, setQuery] = useState('');
	const [chapterMin, setChapterMin] = useState('');
	const [chapterMax, setChapterMax] = useState('');
	const [arcId, setArcId] = useState('');
	const [entityId, setEntityId] = useState('');
	const [chunkKind, setChunkKind] = useState('');
	const [entities, setEntities] = useState<WikiEntity[]>([]);
	const [response, setResponse] = useState<StorySearchResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState('');

	useEffect(() => {
		let alive = true;
		api.entities(storyId, { limit: 200 })
			.then((rows) => { if (alive) setEntities(rows); })
			.catch(() => { if (alive) setEntities([]); });
		return () => { alive = false; };
	}, [storyId]);

	const trimmed = query.trim();
	const filtersActive = Boolean(chapterMin || chapterMax || arcId || entityId || chunkKind);

	useEffect(() => {
		if (trimmed.length < 2) return;
		const controller = new AbortController();
		const timer = window.setTimeout(() => {
			setLoading(true);
			setError('');
			api.searchStory(
				storyId,
				{
					q: trimmed,
					chapterMin: chapterMin ? Number(chapterMin) : undefined,
					chapterMax: chapterMax ? Number(chapterMax) : undefined,
					arcId: arcId || undefined,
					entityId: entityId || undefined,
					chunkKind: chunkKind || undefined,
					limit: 20,
				},
				controller.signal,
			)
				.then((next) => { if (!controller.signal.aborted) setResponse(next); })
				.catch((cause: unknown) => {
					if (controller.signal.aborted) return;
					setResponse(null);
					setError(cause instanceof ApiRequestError ? cause.message : 'Search could not run. Check that memory is indexed for this story.');
				})
				.finally(() => { if (!controller.signal.aborted) setLoading(false); });
		}, 260);
		return () => { window.clearTimeout(timer); controller.abort(); };
	}, [trimmed, storyId, chapterMin, chapterMax, arcId, entityId, chunkKind]);

	const visibleResponse = trimmed.length >= 2 ? response : null;
	const totalMs = useMemo(() => {
		if (!visibleResponse) return 0;
		return Math.round(visibleResponse.timings_ms.total ?? 0);
	}, [visibleResponse]);

	function clearFilters() {
		setChapterMin('');
		setChapterMax('');
		setArcId('');
		setEntityId('');
		setChunkKind('');
	}

	const chapterName = (hit: StorySearchHit) => hit.chapter_title || `Chapter ${hit.chapter_number}`;

	return (
		<section className="story-search" aria-label="Find in story">
			<div className="story-search-intro">
				<div className="eyebrow">FIND IN STORY</div>
				<h2>What does the story remember?</h2>
				<p>Search the same passages the continuity check reads. Results combine meaning, exact words, and names.</p>
			</div>
			<label className="story-search-query">
				<span>Search this story</span>
				<input
					type="search"
					value={query}
					onChange={(event) => setQuery(event.target.value)}
					placeholder="the lantern, Mira's promise, the flooded gate…"
					autoComplete="off"
					aria-label="Search this story"
				/>
			</label>
			<div className="story-search-filters">
				<label>
					<span>Arc</span>
					<select value={arcId} onChange={(event) => setArcId(event.target.value)}>
						<option value="">Any arc</option>
						{arcs.map((arc) => <option value={arc.id} key={arc.id}>{arc.name}</option>)}
					</select>
				</label>
				<label>
					<span>Entity</span>
					<select value={entityId} onChange={(event) => setEntityId(event.target.value)}>
						<option value="">Anyone</option>
						{entities.map((entity) => <option value={entity.id} key={entity.id}>{entity.name}</option>)}
					</select>
				</label>
				<label>
					<span>From chapter</span>
					<input type="number" min={1} max={chapters.at(-1)?.chapter_number ?? undefined} value={chapterMin} onChange={(event) => setChapterMin(event.target.value)} placeholder="1" />
				</label>
				<label>
					<span>Through chapter</span>
					<input type="number" min={1} max={chapters.at(-1)?.chapter_number ?? undefined} value={chapterMax} onChange={(event) => setChapterMax(event.target.value)} placeholder={String(chapters.at(-1)?.chapter_number ?? '')} />
				</label>
				<label>
					<span>Content</span>
					<select value={chunkKind} onChange={(event) => setChunkKind(event.target.value)}>
						<option value="">All indexed</option>
						<option value="scene">Scene prose</option>
					</select>
				</label>
				{filtersActive && <button className="text-button story-search-clear" onClick={clearFilters}>Clear filters</button>}
			</div>

			<div className="story-search-status" role="status" aria-live="polite">
				{trimmed.length < 2 ? 'Type at least two characters.' : loading ? 'Searching…' : visibleResponse ? `${visibleResponse.results.length} passage${visibleResponse.results.length === 1 ? '' : 's'}${totalMs ? ` · ${totalMs} ms` : ''}${visibleResponse.cache_hit ? ' · cached' : ''}` : ''}
			</div>
			{trimmed.length >= 2 && error && <div className="studio-notice error-notice" role="alert">{error}</div>}

			{visibleResponse && visibleResponse.results.length === 0 && !loading && (
				<div className="pane-empty">No passage matched. Try a name, an object, or a phrase you remember.</div>
			)}

			<div className="story-search-results">
				{visibleResponse?.results.map((hit) => {
					const rows = scoreRows(hit);
					return (
						<article className="search-card" key={hit.chunk_id}>
							<div className="search-card-head">
								<div>
									<strong>Chapter {hit.chapter_number}</strong>
									<span>{chapterName(hit)}</span>
								</div>
								<small>lines {hit.start_line}–{hit.end_line}</small>
							</div>
							<blockquote className="search-quote">“{hit.quote}”</blockquote>
							{hit.entities.length > 0 && (
								<div className="search-chips">
									{hit.entities.map((entity) => (
										<button key={entity.id} className="search-chip" onClick={() => setEntityId(entity.id)} title={`Filter by ${entity.name}`}>{entity.name}</button>
									))}
								</div>
							)}
							<div className="search-card-footer">
								<span className="search-score" title="Reciprocal-rank fusion score">{hit.score.toFixed(3)}</span>
								<details className="search-why">
									<summary>Why this matched</summary>
									<dl>
										{rows.map(([key, value]) => <div key={key}><dt>{SCORE_LABEL[key] ?? key}</dt><dd>{value.toFixed(3)}</dd></div>)}
										<div><dt>Merged score</dt><dd>{hit.score.toFixed(3)}</dd></div>
									</dl>
								</details>
								<button className="text-button search-open" onClick={() => onOpen(hit.chapter_id, hit.start_line)}>Open in chapter →</button>
							</div>
						</article>
					);
				})}
			</div>

			{visibleResponse && (
				<details className="search-query-detail">
					<summary>How the query was read</summary>
					<dl>
						<div><dt>Meaning</dt><dd>{visibleResponse.semantic_query || '—'}</dd></div>
						<div><dt>Exact words</dt><dd>{visibleResponse.lexical_query || '—'}</dd></div>
						<div><dt>Names</dt><dd>{visibleResponse.name_query || '—'}</dd></div>
						<div><dt>Entities found</dt><dd>{visibleResponse.entity_ids.length}</dd></div>
					</dl>
				</details>
			)}
		</section>
	);
}
