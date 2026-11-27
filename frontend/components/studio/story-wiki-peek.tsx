"use client";

import { useMemo, useState } from "react";

import { api, type EntityFact, type EntityRelationship, type WikiEntity } from "@/lib/api";

const TYPE_META: Record<string, { label: string; glyph: string; tone: string }> = {
	character: { label: "Characters", glyph: "◉", tone: "rust" },
	location: { label: "Places", glyph: "⌖", tone: "moss" },
	item: { label: "Objects", glyph: "◇", tone: "ochre" },
	world_rule: { label: "Rules", glyph: "⌁", tone: "blue" },
	worldbuilding: { label: "World", glyph: "✳", tone: "violet" },
	power_system: { label: "Powers", glyph: "✦", tone: "gold" },
};

type Detail = { facts: EntityFact[]; outgoing: EntityRelationship[]; incoming: EntityRelationship[] };

export function StoryWikiPeek({ storyId, entities }: { storyId: string; entities: WikiEntity[] }) {
	const [query, setQuery] = useState("");
	const [type, setType] = useState("all");
	const [expanded, setExpanded] = useState<string | null>(null);
	const [details, setDetails] = useState<Record<string, Detail>>({});
	const [loading, setLoading] = useState<string | null>(null);

	const visible = useMemo(() => entities.filter((entity) => {
		const matchesType = type === "all" || entity.entity_type === type;
		const haystack = [entity.name, entity.summary, ...entity.aliases.map((alias) => alias.alias)].join(" ").toLocaleLowerCase();
		return matchesType && haystack.includes(query.trim().toLocaleLowerCase());
	}), [entities, query, type]);

	const open = async (entity: WikiEntity) => {
		if (expanded === entity.id) { setExpanded(null); return; }
		setExpanded(entity.id);
		if (details[entity.id]) return;
		setLoading(entity.id);
		try {
			const [facts, relationships] = await Promise.all([api.entityFacts(entity.id), api.entityRelationships(entity.id)]);
			setDetails((current) => ({ ...current, [entity.id]: { facts: facts.filter((fact) => fact.status === "accepted" || fact.status === "proposed").slice(0, 8), outgoing: relationships.outgoing.slice(0, 8), incoming: relationships.incoming.slice(0, 8) } }));
		} catch {
			setDetails((current) => ({ ...current, [entity.id]: { facts: [], outgoing: [], incoming: [] } }));
		} finally {
			setLoading(null);
		}
	};

	return (
		<div className="wiki-peek">
			<div className="wiki-peek-search">
				<span aria-hidden="true">⌕</span>
				<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search the story bible" aria-label="Search wiki entries" />
				<span>{visible.length}</span>
			</div>
			<div className="wiki-peek-types" role="tablist" aria-label="Entry types">
				<button className={type === "all" ? "active" : ""} onClick={() => setType("all")}>All</button>
				{Object.entries(TYPE_META).map(([id, meta]) => <button key={id} className={type === id ? "active" : ""} onClick={() => setType(id)}>{meta.glyph} {meta.label}</button>)}
			</div>
			{visible.length === 0 ? (
				<div className="wiki-peek-empty"><span aria-hidden="true">✳</span><strong>{entities.length ? "No one by that name." : "The cast is still offstage."}</strong><p>{entities.length ? "Try another search, or lift the type filter." : "Select a name in the paper, capture what the story knows, then accept it into canon."}</p></div>
			) : (
				<div className="wiki-peek-list">
					{visible.slice(0, 40).map((entity) => {
						const meta = TYPE_META[entity.entity_type] ?? { label: entity.entity_type, glyph: "·", tone: "moss" };
						const isOpen = expanded === entity.id;
						const detail = details[entity.id];
						return (
							<article className={`wiki-peek-card tone-${meta.tone}${isOpen ? " is-open" : ""}`} key={entity.id}>
								<button className="wiki-peek-card-main" onClick={() => void open(entity)} aria-expanded={isOpen}>
									<span className="wiki-peek-avatar">{entity.name.slice(0, 1)}</span>
									<span className="wiki-peek-copy">
										<span className="wiki-peek-name">{entity.name}</span>
										<small>{meta.label} · {entity.aliases.length ? entity.aliases.slice(0, 2).map((alias) => alias.alias).join(", ") : "no aliases yet"}</small>
									</span>
									<span className="wiki-peek-chevron">{isOpen ? "−" : "+"}</span>
								</button>
								<p>{entity.summary || "No summary yet. Select a passage in the paper to add one."}</p>
								{isOpen && (
									<div className="wiki-peek-detail">
										{loading === entity.id ? <span className="tiny-spinner" /> : <>
											{detail?.facts.length ? <div className="wiki-peek-facts"><span>Canon facts</span>{detail.facts.map((fact) => <p key={fact.id}>{fact.predicate.replaceAll("_", " ")}: <b>{fact.value_text ?? fact.value_number ?? fact.value_date ?? "—"}</b></p>)}</div> : <p className="wiki-peek-muted">No accepted facts yet.</p>}
											{detail && detail.outgoing.length + detail.incoming.length > 0 ? <div className="wiki-peek-links"><span>Threads to</span>{[...detail.outgoing, ...detail.incoming].slice(0, 6).map((link) => <em key={link.id}>{link.relationship_type.replaceAll("_", " ")}</em>)}</div> : null}
										</>}
										<a className="text-button" href={`/stories/${storyId}/wiki/${entity.id}`}>Open full entry ↗</a>
									</div>
								)}
							</article>
						);
					})}
				</div>
			)}
		</div>
	);
}
