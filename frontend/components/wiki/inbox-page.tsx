"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { useInbox, useStory } from "@/components/wiki/use-wiki";
import { api, type InboxItem } from "@/lib/api";
import { qk } from "@/lib/query-keys";

type KindFilter = "all" | "fact" | "merge" | "finding";

interface Rules {
	require_quote: boolean;
	min_confidence: number;
	require_existing_entity: boolean;
	block_conflicts: boolean;
	max_per_chapter: number;
}

const RULE_DEFAULTS: Rules = {
	require_quote: true,
	min_confidence: 80,
	require_existing_entity: false,
	block_conflicts: true,
	max_per_chapter: 20,
};

export function InboxPage({ storyId }: { storyId: string }) {
	const queryClient = useQueryClient();
	const story = useStory(storyId);
	const inbox = useInbox(storyId);
	const [kind, setKind] = useState<KindFilter>("all");
	const [chapterFilter, setChapterFilter] = useState("");
	const [entityQuery, setEntityQuery] = useState("");
	const [minConfidence, setMinConfidence] = useState(0);
	const [selected, setSelected] = useState<string[]>([]);
	const [cursor, setCursor] = useState(0);
	const [showRules, setShowRules] = useState(false);

	const items = useMemo(() => {
		const all = inbox.data?.items ?? [];
		const needle = entityQuery.trim().toLocaleLowerCase();
		return all.filter((item) => {
			if (kind !== "all" && item.kind !== kind) return false;
			if (chapterFilter && item.source.chapter_number !== Number(chapterFilter)) return false;
			if (minConfidence && item.confidence < minConfidence) return false;
			if (needle && !`${item.title} ${item.summary}`.toLocaleLowerCase().includes(needle)) return false;
			return true;
		});
	}, [inbox.data, kind, chapterFilter, entityQuery, minConfidence]);

	const chapterOptions = useMemo(() => {
		const numbers = new Set<number>();
		for (const item of inbox.data?.items ?? []) {
			if (item.source.chapter_number) numbers.add(item.source.chapter_number);
		}
		return [...numbers].sort((a, b) => a - b);
	}, [inbox.data]);

	const counts = useMemo(() => {
		const all = inbox.data?.items ?? [];
		return {
			all: all.length,
			fact: all.filter((item) => item.kind === "fact").length,
			merge: all.filter((item) => item.kind === "merge").length,
			finding: all.filter((item) => item.kind === "finding").length,
		};
	}, [inbox.data]);

	const refresh = async () => {
		await Promise.all([
			queryClient.invalidateQueries({ queryKey: qk.inbox(storyId) }),
			queryClient.invalidateQueries({ queryKey: qk.entityList(storyId) }),
		]);
		setSelected([]);
	};

	const decide = useMutation({
		mutationFn: ({ ids, action }: { ids: string[]; action: string }) =>
			api.inboxDecide(storyId, ids, action),
		// Remove decided items from the cached list at once; a review list must keep up.
		onMutate: async ({ ids }) => {
			const key = qk.inbox(storyId);
			await queryClient.cancelQueries({ queryKey: key });
			const previous = queryClient.getQueryData(key);
			queryClient.setQueryData(key, (current: { items: InboxItem[]; next_cursor: string | null } | undefined) =>
				current ? { ...current, items: current.items.filter((item) => !ids.includes(item.id)) } : current,
			);
			return { previous };
		},
		onError: (_error, _vars, context) => {
			if (context?.previous) queryClient.setQueryData(qk.inbox(storyId), context.previous);
		},
		onSuccess: async (result) => {
			const total = result.facts + result.findings + result.merges;
			toast.success(`${total} ${total === 1 ? "item" : "items"} decided.`);
			await refresh();
		},
	});

	const decideOne = (item: InboxItem, actions: string[]) => {
		const action = item.kind === "finding" ? (actions.includes("resolve") ? "resolve" : "dismiss") : actions[0];
		decide.mutate({ ids: [item.id], action });
	};

	const decideSelected = (action: string) => {
		if (!selected.length) return;
		decide.mutate({ ids: selected, action });
	};

	// Keyboard: j/k move, a accept, x reject, space select.
	useEffect(() => {
		function onKeyDown(event: KeyboardEvent) {
			const target = event.target as HTMLElement | null;
			if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) return;
			if (!items.length) return;
			const current = items[cursor];
			if (event.key === "j" || event.key === "ArrowDown") {
				event.preventDefault();
				setCursor((value) => Math.min(value + 1, items.length - 1));
			} else if (event.key === "k" || event.key === "ArrowUp") {
				event.preventDefault();
				setCursor((value) => Math.max(value - 1, 0));
			} else if (event.key === "a" && current) {
				event.preventDefault();
				decide.mutate({ ids: [current.id], action: current.kind === "finding" ? "resolve" : "accept" });
			} else if (event.key === "x" && current) {
				event.preventDefault();
				decide.mutate({ ids: [current.id], action: "dismiss" });
			} else if (event.key === "e" && current && current.entity_id) {
				event.preventDefault();
				window.location.assign(`/stories/${storyId}/wiki/${current.entity_id}`);
			} else if (event.key === " " && current) {
				event.preventDefault();
				setSelected((value) => (value.includes(current.id) ? value.filter((id) => id !== current.id) : [...value, current.id]));
			}
		}
		document.addEventListener("keydown", onKeyDown);
		return () => document.removeEventListener("keydown", onKeyDown);
	});

	return (
		<div className="wiki-page">
			<header className="wiki-page-head">
				<div>
					<div className="eyebrow">DECISIONS WAITING</div>
					<h1>Review inbox</h1>
				</div>
				<div className="inbox-actions">
					<button className="quiet-button" onClick={() => setShowRules((value) => !value)}>
						Auto-accept rules
					</button>
				</div>
			</header>

			<div className="inbox-filters">
				<div className="inbox-tabs" role="tablist" aria-label="Kinds of review item">
					{(["all", "fact", "merge", "finding"] as KindFilter[]).map((value) => (
						<button
							key={value}
							role="tab"
							aria-selected={kind === value}
							className={kind === value ? "active" : ""}
							onClick={() => {
								setKind(value);
								setCursor(0);
							}}
						>
							{value === "all" ? "Everything" : value === "fact" ? "Facts" : value === "merge" ? "Merges" : "Continuity"}
							<span>{counts[value]}</span>
						</button>
					))}
				</div>
				<label className="inbox-chapter-filter">
					<input
						type="search"
						value={entityQuery}
						onChange={(event) => setEntityQuery(event.target.value)}
						placeholder="Entry or wording"
						aria-label="Filter by entry"
					/>
					<span>Chapter</span>
					<select value={chapterFilter} onChange={(event) => setChapterFilter(event.target.value)}>
						<option value="">Every chapter</option>
						{chapterOptions.map((number) => (
							<option key={number} value={number}>
								Chapter {number}
							</option>
						))}
					</select>
				</label>
				<label className="inbox-chapter-filter">
					<span>At least</span>
					<select value={minConfidence} onChange={(event) => setMinConfidence(Number(event.target.value))}>
						<option value={0}>Any confidence</option>
						<option value={50}>50%</option>
						<option value={80}>80%</option>
						<option value={90}>90%</option>
					</select>
				</label>
				<button
					className="text-button subtle"
					onClick={() => setSelected(selected.length === items.length ? [] : items.map((item) => item.id))}
				>
					{selected.length === items.length && items.length > 0 ? "Clear selection" : "Select all shown"}
				</button>
			</div>

			{selected.length > 0 && (
				<div className="inbox-batch" role="status">
					<span>{selected.length} selected</span>
					<button className="button button-approve" onClick={() => decideSelected("accept")}>
						Accept selected
					</button>
					<button className="quiet-button" onClick={() => decideSelected("dismiss")}>
						Reject selected
					</button>
					<button className="text-button subtle" onClick={() => setSelected([])}>
						Clear
					</button>
				</div>
			)}

			{showRules && <AutoAcceptPanel storyId={storyId} onRan={refresh} />}

			{inbox.isPending ? (
				<p className="wiki-quiet">Collecting what needs a decision…</p>
			) : !items.length ? (
				<div className="wiki-empty">
					<h2>Nothing is waiting.</h2>
					<p>New proposals and continuity findings appear here as you write.</p>
				</div>
			) : (
				<ul className="inbox-list">
					{items.map((item, index) => (
						<li
							key={item.id}
							className={`inbox-item kind-${item.kind}${index === cursor ? " selected" : ""}`}
						>
							<input
								type="checkbox"
								checked={selected.includes(item.id)}
								onChange={() =>
									setSelected((value) =>
										value.includes(item.id) ? value.filter((id) => id !== item.id) : [...value, item.id],
									)
								}
								aria-label={`Select ${item.title}`}
							/>
							<div className="inbox-body">
								<div className="inbox-head">
									<span className={`inbox-kind kind-${item.kind}`}>{item.kind}</span>
									<strong>{item.title}</strong>
									<span className="inbox-confidence">{item.confidence}%</span>
								</div>
								<p className="inbox-summary">{item.summary}</p>
								{item.source.chapter_number && (
									<Link
										className="provenance-chip"
										href={`/stories/${storyId}?chapter=${item.source.chapter_id}${item.source.line ? `&line=${item.source.line}` : ""}`}
									>
										Ch. {item.source.chapter_number}
										{item.source.line ? ` · line ${item.source.line}` : ""}
										{item.source.quote ? ` · “${item.source.quote.slice(0, 42)}…”` : ""}
									</Link>
								)}
								{item.why_held && <p className="inbox-why">{item.why_held}</p>}
								<div className="inbox-item-actions">
									{item.kind === "fact" && (
										<>
											<button className="button button-approve" onClick={() => decideOne(item, ["accept"])}>
												Accept
											</button>
											<button className="quiet-button" onClick={() => decideOne(item, ["reject"])}>
												Reject
											</button>
											{item.entity_id && (
												<Link className="text-button" href={`/stories/${storyId}/wiki/${item.entity_id}`}>
													Open entry
												</Link>
											)}
										</>
									)}
									{item.kind === "merge" && (
										<>
											<Link className="button button-approve" href={`/stories/${storyId}/wiki/${item.entity_id}`}>
												Review merge
											</Link>
											<button className="quiet-button" onClick={() => decideOne(item, ["dismiss"])}>
												Not the same
											</button>
										</>
									)}
									{item.kind === "finding" && (
										<>
											<button className="button button-approve" onClick={() => decideOne(item, ["resolve"])}>
												It is a problem
											</button>
											<button className="quiet-button" onClick={() => decideOne(item, ["dismiss"])}>
												On purpose
											</button>
										</>
									)}
								</div>
							</div>
						</li>
					))}
				</ul>
			)}
			<p className="wiki-keys-hint">
				<kbd>j</kbd>/<kbd>k</kbd> move · <kbd>a</kbd> accept · <kbd>x</kbd> reject · <kbd>e</kbd> edit · <kbd>space</kbd> select
			</p>
			<p className="wiki-quiet">
				{story.data ? `Story: ${story.data.title}. ` : ""}Nothing becomes canon without a decision unless auto-accept rules say otherwise.
			</p>
		</div>
	);
}

function AutoAcceptPanel({ storyId, onRan }: { storyId: string; onRan: () => Promise<void> }) {
	const queryClient = useQueryClient();
	const rules = useQuery({
		queryKey: [...qk.inbox(storyId), "rules"],
		queryFn: () => api.autoAcceptRules(storyId),
	});
	const preview = useQuery({
		queryKey: [...qk.inbox(storyId), "rules", "preview"],
		queryFn: () => api.autoAcceptPreview(storyId),
	});
	const [draft, setDraft] = useState<Rules | null>(null);
	const current = draft ?? rules.data ?? RULE_DEFAULTS;

	const save = useMutation({
		mutationFn: (next: Rules) => api.saveAutoAcceptRules(storyId, next),
		onSuccess: async () => {
			toast.success("Rules updated.");
			await queryClient.invalidateQueries({ queryKey: [...qk.inbox(storyId), "rules"] });
		},
	});

	const run = useMutation({
		mutationFn: () => api.runAutoAccept(storyId),
		onSuccess: async (result) => {
			toast.success(`${result.accepted} accepted, ${result.held} still held.`);
			await onRan();
			await queryClient.invalidateQueries({ queryKey: [...qk.inbox(storyId), "rules"] });
		},
	});

	const update = (changes: Partial<Rules>) => setDraft({ ...current, ...changes });

	return (
		<section className="inbox-rules" aria-labelledby="rules-heading">
			<header className="wiki-section-head">
				<h2 id="rules-heading">Auto-accept rules</h2>
				<button
					className="button button-approve"
					disabled={save.isPending}
					onClick={() => save.mutate(current)}
				>
					Save rules
				</button>
			</header>
			<div className="rules-grid">
				<label className="rule-toggle">
					<input
						type="checkbox"
						checked={current.require_quote}
						onChange={(event) => update({ require_quote: event.target.checked })}
					/>
					<span>
						<strong>Quote must exist in the chapter</strong>
						<small>The fact has to point at real text.</small>
					</span>
				</label>
				<label className="rule-toggle">
					<input
						type="checkbox"
						checked={current.block_conflicts}
						onChange={(event) => update({ block_conflicts: event.target.checked })}
					/>
					<span>
						<strong>Never contradict accepted canon</strong>
						<small>A different value for a known fact stays for review.</small>
					</span>
				</label>
				<label className="rule-toggle">
					<input
						type="checkbox"
						checked={current.require_existing_entity}
						onChange={(event) => update({ require_existing_entity: event.target.checked })}
					/>
					<span>
						<strong>The entry must already exist</strong>
						<small>Do not grow the wiki automatically.</small>
					</span>
				</label>
				<label className="rule-number">
					<span>Confidence threshold</span>
					<input
						type="number"
						min={0}
						max={100}
						value={current.min_confidence}
						onChange={(event) => update({ min_confidence: Number(event.target.value) })}
					/>
				</label>
				<label className="rule-number">
					<span>Maximum per chapter</span>
					<input
						type="number"
						min={1}
						max={500}
						value={current.max_per_chapter}
						onChange={(event) => update({ max_per_chapter: Number(event.target.value) })}
					/>
				</label>
			</div>
			<div className="rules-preview" role="status" aria-live="polite">
				{preview.isPending ? (
					"Counting what these rules would do…"
				) : preview.data ? (
					<>
						With these rules, <strong>{preview.data.would_accept}</strong> of {preview.data.total} waiting items
						would be accepted now; {preview.data.held} stay for review.
					</>
				) : (
					"Preview unavailable."
				)}
				<button className="button button-quiet" disabled={run.isPending} onClick={() => run.mutate()}>
					{run.isPending ? "Applying…" : "Apply now"}
				</button>
			</div>
			<p className="wiki-quiet">
				Saving rules changes the preview only. Nothing is accepted until you press Apply now.
			</p>
		</section>
	);
}
