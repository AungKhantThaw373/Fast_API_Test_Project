'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { api, type Chapter, type ChapterSynopsis, type StoryArc, type StorySoFar } from '@/lib/api';

interface RecapPanelProps {
	storyId: string;
	chapter: Chapter;
	arcs: StoryArc[];
	onOpenCitation: (chapterId: string, line: number) => void;
}

export function RecapPanel({ storyId, chapter, arcs, onOpenCitation }: RecapPanelProps) {
	const [synopsis, setSynopsis] = useState<ChapterSynopsis | null>(null);
	const [draft, setDraft] = useState('');
	const [saving, setSaving] = useState(false);
	const [generating, setGenerating] = useState(false);
	const [recap, setRecap] = useState<StorySoFar | null>(null);
	const [limit, setLimit] = useState(5);
	const [arcFilter, setArcFilter] = useState('');
	const [arcSummaryOverride, setArcSummaryOverride] = useState<{ arcId: string; summary: string } | null>(null);
	const [summarizingArc, setSummarizingArc] = useState(false);

	useEffect(() => {
		let cancelled = false;
		void api.chapterSynopsis(chapter.id).then((value) => {
			if (cancelled) return;
			setSynopsis(value);
			setDraft(value.synopsis);
		}).catch((error: unknown) => {
			if (!cancelled) toast.error(error instanceof Error ? error.message : 'Could not read the chapter synopsis.');
		});
		return () => { cancelled = true; };
	}, [chapter.id]);

	useEffect(() => {
		let cancelled = false;
		void api.storySoFar(storyId, limit, arcFilter || undefined).then((value) => {
			if (!cancelled) setRecap(value);
		}).catch((error: unknown) => {
			if (!cancelled) toast.error(error instanceof Error ? error.message : 'Could not build the recap.');
		});
		return () => { cancelled = true; };
	}, [arcFilter, limit, storyId]);

	const currentArc = arcs.find((arc) => arc.id === chapter.arc_id) ?? null;
	const arcSummary = currentArc && arcSummaryOverride?.arcId === currentArc.id ? arcSummaryOverride.summary : currentArc?.summary ?? '';

	async function saveSynopsis() {
		if (!synopsis || draft.trim() === synopsis.synopsis.trim()) return;
		setSaving(true);
		try {
			const saved = await api.updateChapterSynopsis(chapter.id, draft);
			setSynopsis(saved);
			setDraft(saved.synopsis);
			toast.success('Synopsis saved.');
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Could not save the synopsis.');
		} finally {
			setSaving(false);
		}
	}

	async function generateSynopsis() {
		setGenerating(true);
		try {
			const generated = await api.generateChapterSynopsis(chapter.id, Boolean(synopsis?.synopsis.trim()));
			setSynopsis(generated);
			setDraft(generated.synopsis);
			toast.success(generated.generated ? 'Synopsis generated from the chapter.' : 'Synopsis is already up to date.');
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Could not generate the synopsis.');
		} finally {
			setGenerating(false);
		}
	}

	async function summarizeArc() {
		if (!currentArc) return;
		setSummarizingArc(true);
		try {
			const result = await api.generateArcSummary(storyId, currentArc.id);
			setArcSummaryOverride({ arcId: result.arc_id, summary: result.summary });
			setRecap((current) => current ? { ...current, arcs: current.arcs.map((arc) => arc.arc_id === result.arc_id ? { ...arc, summary: result.summary } : arc) } : current);
			toast.success(`Arc summary written from ${result.chapter_count} chapters.`);
		} catch (error) {
			toast.error(error instanceof Error ? error.message : 'Could not summarize the arc.');
		} finally {
			setSummarizingArc(false);
		}
	}

	return (
		<section className="recap-panel" aria-label="Recaps">
			<div className="recap-chapter">
				<div className="pane-section-title">
					<strong>Chapter {chapter.chapter_number} synopsis</strong>
					<span>{synopsis?.generated ? 'generated' : 'yours'}</span>
				</div>
				<p className="pane-hint">A short memory of this chapter. Edit it freely; generation never runs unless you ask.</p>
				<textarea
					className="recap-editor"
					aria-label={`Synopsis for chapter ${chapter.chapter_number}`}
					value={draft}
					onChange={(event) => setDraft(event.target.value)}
					placeholder="What changed in this chapter?"
					rows={7}
					disabled={!synopsis}
				/>
				<div className="recap-actions">
					<button type="button" className="button-primary" onClick={() => void saveSynopsis()} disabled={saving || !synopsis || draft.trim() === synopsis.synopsis.trim()}>{saving ? 'Saving…' : 'Save synopsis'}</button>
					<button type="button" className="text-button" onClick={() => void generateSynopsis()} disabled={generating}>{generating ? 'Reading…' : synopsis?.synopsis.trim() ? 'Regenerate' : 'Generate'}</button>
				</div>
			</div>

			{currentArc && (
				<div className="recap-arc">
					<div className="pane-section-title"><strong>{currentArc.name} arc</strong><span>{currentArc.chapter_count} chapters</span></div>
					{arcSummary ? <p className="recap-arc-summary">{arcSummary}</p> : <p className="pane-hint">No arc summary yet. Build one from the chapter synopses in this arc.</p>}
					<button type="button" className="text-button" onClick={() => void summarizeArc()} disabled={summarizingArc}>{summarizingArc ? 'Building arc…' : arcSummary ? 'Rebuild arc summary' : 'Summarize arc'}</button>
				</div>
			)}

			<div className="recap-so-far">
				<div className="pane-section-title">
					<strong>Story so far</strong>
					<span>read-only</span>
				</div>
				<div className="recap-controls">
					<label>Last
						<select value={limit} onChange={(event) => setLimit(Number(event.target.value))} aria-label="How many chapters to recap">
							<option value={3}>3 chapters</option>
							<option value={5}>5 chapters</option>
							<option value={10}>10 chapters</option>
						</select>
					</label>
					<label>Arc
						<select value={arcFilter} onChange={(event) => setArcFilter(event.target.value)} aria-label="Limit recap to an arc">
							<option value="">Whole story</option>
							{arcs.map((arc) => <option key={arc.id} value={arc.id}>{arc.name}</option>)}
						</select>
					</label>
				</div>
				{recap && recap.chapters.length > 0 ? (
					<>
						{recap.range_label && <p className="recap-range">{recap.range_label}</p>}
						<ol className="recap-list">
							{recap.chapters.map((row) => (
								<li key={row.chapter_id}>
									<strong>Ch. {row.chapter_number} · {row.title}</strong>
									<p>{row.synopsis || 'No synopsis yet.'}</p>
									<button type="button" className="recap-citation" onClick={() => onOpenCitation(row.citation.chapter_id, row.citation.line)} title={`Open chapter ${row.citation.chapter_number} at line ${row.citation.line}`}>“{row.citation.quote}” <span>L{row.citation.line}</span></button>
								</li>
							))}
						</ol>
					</>
				) : <p className="pane-empty">No chapters to recap yet.</p>}
				{recap?.arcs.filter((arc) => arc.summary.trim()).map((arc) => (
					<article className="recap-arc-read" key={arc.arc_id}>
						<strong>{arc.name}</strong>
						<p>{arc.summary}</p>
					</article>
				))}
			</div>
		</section>
	);
}