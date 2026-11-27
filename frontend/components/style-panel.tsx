'use client';

import { useMemo, useState } from 'react';

import { STYLE_CATEGORY_LABELS, type StyleCategory, type StyleIssue, type StyleReport } from '@/lib/style-analysis';

interface StylePanelProps {
	report: StyleReport | null;
	issues: StyleIssue[];
	dismissedCount: number;
	onJump: (issue: StyleIssue) => void;
	onDismiss: (issue: StyleIssue) => void;
	onDismissPattern: (issue: StyleIssue) => void;
	onReset: () => void;
}

const ORDER: StyleCategory[] = ['opening', 'crutch', 'filter', 'adverb', 'passive', 'dialogue', 'pov', 'tense', 'paragraph'];

export function StylePanel({ report, issues, dismissedCount, onJump, onDismiss, onDismissPattern, onReset }: StylePanelProps) {
	const [hidden, setHidden] = useState<Set<StyleCategory>>(() => new Set());
	const counts = useMemo(() => {
		const next = new Map<StyleCategory, number>();
		for (const issue of issues) next.set(issue.category, (next.get(issue.category) ?? 0) + 1);
		return next;
	}, [issues]);
	const visible = useMemo(() => issues.filter((issue) => !hidden.has(issue.category)), [hidden, issues]);
	const grouped = useMemo(() => ORDER.map((category) => ({ category, items: visible.filter((issue) => issue.category === category) })).filter((group) => group.items.length > 0), [visible]);

	if (!report) {
		return <div className="pane-empty">Open a chapter to read its style.</div>;
	}

	return (
		<section className="style-panel" aria-label="Style and line edits">
			<div className="pane-section-title"><strong>Style, quietly</strong><span>{report.stats.words.toLocaleString()} words</span></div>
			<p className="pane-hint">Observations only. Nothing here changes your text. Choose a line to find it in the manuscript.</p>
			<dl className="style-stats">
				<div><dt>Reading ease</dt><dd>{report.stats.fleschReadingEase}</dd></div>
				<div><dt>Grade</dt><dd>{report.stats.fleschKincaidGrade}</dd></div>
				<div><dt>Avg. sentence</dt><dd>{report.stats.averageSentenceWords} words</dd></div>
				<div><dt>Longest paragraph</dt><dd>{report.stats.longestParagraphWords} words</dd></div>
			</dl>
			<div className="style-filters" aria-label="Filter style observations">
				{ORDER.filter((category) => counts.has(category)).map((category) => (
					<button
						key={category}
						type="button"
						className={hidden.has(category) ? 'style-filter' : 'style-filter is-on'}
						aria-pressed={!hidden.has(category)}
						onClick={() => setHidden((current) => {
							const next = new Set(current);
							if (next.has(category)) next.delete(category);
							else next.add(category);
							return next;
						})}
					>
						{STYLE_CATEGORY_LABELS[category]} <span>{counts.get(category)}</span>
					</button>
				))}
			</div>
			{dismissedCount > 0 && <div className="style-dismissed"><span>{dismissedCount} muted</span><button type="button" className="text-button" onClick={onReset}>Restore all</button></div>}
			{grouped.length === 0
				? <div className="pane-empty">No quiet observations in this chapter. That is allowed.</div>
				: <div className="style-groups">
					{grouped.map((group) => (
						<section className="style-group" key={group.category}>
							<h3>{STYLE_CATEGORY_LABELS[group.category]} <span>{group.items.length}</span></h3>
							<ul>
								{group.items.slice(0, 40).map((issue) => (
									<li key={issue.id}>
										<button type="button" className="style-find" onClick={() => onJump(issue)} title={`Line ${issue.line}`}>
											<span className="style-line">L{issue.line}</span>
											<span className="style-quote">“{issue.excerpt}”</span>
										</button>
										<p>{issue.message}</p>
										<div className="style-actions">
											<button type="button" className="text-button subtle" onClick={() => onDismiss(issue)}>Dismiss this</button>
											<button type="button" className="text-button subtle" onClick={() => onDismissPattern(issue)}>Mute pattern</button>
										</div>
									</li>
								))}
							</ul>
						</section>
					))}
				</div>}
		</section>
	);
}