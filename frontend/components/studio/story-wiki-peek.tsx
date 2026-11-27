"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
	api,
	type EntityAppearance,
	type EntityFact,
	type EntityRelationship,
	type WikiEntity,
	type WikiThread,
} from "@/lib/api";

const TYPE_META: Record<string, { label: string; glyph: string; tone: string }> = {
	character: { label: "Character", glyph: "◉", tone: "rust" },
	location: { label: "Place", glyph: "⌖", tone: "moss" },
	item: { label: "Object", glyph: "◇", tone: "ochre" },
	organization: { label: "Organization", glyph: "⬡", tone: "violet" },
	concept: { label: "Concept", glyph: "⌁", tone: "blue" },
	world_rule: { label: "Rule", glyph: "⌁", tone: "blue" },
	power_system: { label: "Power", glyph: "✦", tone: "gold" },
	creature: { label: "Creature", glyph: "◬", tone: "rust" },
	other: { label: "Other", glyph: "·", tone: "moss" },
};

type Detail = {
	entity: WikiEntity;
	facts: EntityFact[];
	outgoing: EntityRelationship[];
	incoming: EntityRelationship[];
	appearances: EntityAppearance[];
	threads: WikiThread[];
};

function chapterLabel(number: number, title: string) {
	return title && title !== `Chapter ${number}` ? `Ch. ${number} · ${title}` : `Chapter ${number}`;
}

function uniqueChapters(appearances: EntityAppearance[]) {
	const chapters = new Map<string, EntityAppearance>();
	for (const appearance of appearances) {
		if (!chapters.has(appearance.chapter_id)) chapters.set(appearance.chapter_id, appearance);
	}
	return [...chapters.values()].sort((a, b) => a.chapter_number - b.chapter_number);
}

export function StoryWikiPeek({
	storyId,
	entities,
	focusEntityId,
}: {
	storyId: string;
	entities: WikiEntity[];
	focusEntityId?: string | null;
}) {
	const [query, setQuery] = useState("");
	const [type, setType] = useState("all");
	const [selectedId, setSelectedId] = useState<string | null>(focusEntityId ?? null);

	const visible = useMemo(() => entities.filter((entity) => {
		const matchesType = type === "all" || entity.entity_type === type;
		const haystack = [entity.name, entity.summary, ...entity.aliases.map((alias) => alias.alias)].join(" ").toLocaleLowerCase();
		return matchesType && haystack.includes(query.trim().toLocaleLowerCase());
	}), [entities, query, type]);

	const names = useMemo(() => new Map(entities.map((entity) => [entity.id, entity.name])), [entities]);

	const { data: detail = null, isFetching: loading, error } = useQuery({
		queryKey: ["studio-wiki-entry", storyId, selectedId],
		enabled: Boolean(selectedId),
		staleTime: 30_000,
		queryFn: async (): Promise<Detail> => {
			const entityId = selectedId as string;
			const [entity, facts, relationships, appearances, threads] = await Promise.all([
				api.entity(entityId),
				api.entityFacts(entityId),
				api.entityRelationships(entityId),
				api.entityAppearances(entityId),
				api.threads(storyId),
			]);
			return {
				entity,
				facts: facts.filter((fact) => fact.status === "accepted" || fact.status === "proposed"),
				outgoing: relationships.outgoing,
				incoming: relationships.incoming,
				appearances,
				threads: threads.filter((thread) => thread.linked_entity_ids.includes(entityId)),
			};
		},
	});

	const selected = detail?.entity ?? entities.find((entity) => entity.id === selectedId) ?? null;
	const meta = selected ? TYPE_META[selected.entity_type] ?? TYPE_META.other : TYPE_META.other;
	const selectedFacts = detail?.facts.slice().sort((a, b) => a.predicate.localeCompare(b.predicate)) ?? [];
	const chapters = detail ? uniqueChapters(detail.appearances) : [];

	if (selected) {
		return (
			<div className="wiki-peek wiki-peek-dossier-view">
				<button className="wiki-dossier-back" onClick={() => setSelectedId(null)}>
					<span aria-hidden="true">←</span> All entries
				</button>
				<article className="wiki-dossier">
					<header className="wiki-dossier-head">
						<div className={`wiki-dossier-kicker tone-${meta.tone}`}><span aria-hidden="true">{meta.glyph}</span> {meta.label}<i>·</i>{selected.status}</div>
						<h2>{selected.name}</h2>
						{selected.aliases.length > 0 && (
							<p className="wiki-dossier-aka"><span>Also known as</span> {selected.aliases.map((alias) => alias.alias).join(" · ")}</p>
						)}
						<p className="wiki-dossier-lead">{selected.summary || "No summary yet. This entry is waiting for someone to write it down."}</p>
					</header>

					<dl className="wiki-dossier-meta">
						<div><dt>Type</dt><dd>{meta.label}</dd></div>
						<div><dt>First seen</dt><dd>{selected.first_chapter_number ? `Chapter ${selected.first_chapter_number}` : "Not yet placed"}</dd></div>
						<div><dt>Last seen</dt><dd>{selected.last_chapter_number ? `Chapter ${selected.last_chapter_number}` : "—"}</dd></div>
						<div><dt>Appearances</dt><dd>{chapters.length || "—"}</dd></div>
					</dl>

					{loading && <p className="wiki-dossier-note"><span className="tiny-spinner" /> Reading the entry…</p>}
					{error && <p className="form-error">{error.message}</p>}

					{detail && (
						<>
							<section className="wiki-dossier-section">
								<h3>Facts</h3>
								{selectedFacts.length ? (
									<dl className="wiki-dossier-lines">
										{selectedFacts.map((fact) => (
											<div key={fact.id}>
												<dt>{fact.predicate.replaceAll("_", " ")}</dt>
												<dd>{fact.value_text ?? fact.value_number ?? fact.value_date ?? (fact.value_entity_id ? names.get(fact.value_entity_id) ?? "Linked entry" : "—")}{fact.status === "proposed" && <em> proposed</em>}</dd>
											</div>
										))}
									</dl>
								) : <p className="wiki-dossier-note">No facts recorded yet.</p>}
							</section>

							<section className="wiki-dossier-section">
								<h3>Relationships</h3>
								{detail.outgoing.length + detail.incoming.length ? (
									<ul className="wiki-dossier-lines wiki-dossier-relations">
										{detail.outgoing.map((relation) => (
											<li key={relation.id}><b>{relation.relationship_type.replaceAll("_", " ")}</b><span>{names.get(relation.to_entity_id) ?? "Unknown entry"}</span>{relation.since_chapter ? <em>since ch. {relation.since_chapter}</em> : null}</li>
										))}
										{detail.incoming.map((relation) => (
											<li key={relation.id}><b>{relation.relationship_type.replaceAll("_", " ")}</b><span>{names.get(relation.from_entity_id) ?? "Unknown entry"}</span><em>incoming</em></li>
										))}
									</ul>
								) : <p className="wiki-dossier-note">No relationships drawn yet.</p>}
							</section>

							<section className="wiki-dossier-section">
								<h3>Appearances</h3>
								{chapters.length ? (
									<ol className="wiki-dossier-chapters">
										{chapters.map((chapter) => (
											<li key={chapter.chapter_id}><span>{String(chapter.chapter_number).padStart(2, "0")}</span>{chapterLabel(chapter.chapter_number, chapter.chapter_title)}</li>
										))}
									</ol>
								) : <p className="wiki-dossier-note">Not seen in a chapter yet.</p>}
							</section>

							<section className="wiki-dossier-section">
								<h3>Threads</h3>
								{detail.threads.length ? (
									<ul className="wiki-dossier-threads">
										{detail.threads.map((thread) => (
											<li key={thread.id}><b>{thread.title}</b><span>{thread.description}</span><em>{thread.state}</em></li>
										))}
									</ul>
								) : <p className="wiki-dossier-note">No open promises attached.</p>}
							</section>
						</>
					)}
				</article>
			</div>
		);
	}

	return (
		<div className="wiki-peek">
			<div className="wiki-peek-search">
				<span aria-hidden="true">⌕</span>
				<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search the story bible" aria-label="Search wiki entries" />
				<span>{visible.length}</span>
			</div>
			<div className="wiki-peek-types" role="tablist" aria-label="Entry types">
				<button className={type === "all" ? "active" : ""} onClick={() => setType("all")}>All</button>
				{Object.entries(TYPE_META).map(([id, entry]) => <button key={id} className={type === id ? "active" : ""} onClick={() => setType(id)}>{entry.glyph} {entry.label}</button>)}
			</div>
			{visible.length === 0 ? (
				<div className="wiki-peek-empty"><span aria-hidden="true">✳</span><strong>{entities.length ? "No one by that name." : "The cast is still offstage."}</strong><p>{entities.length ? "Try another search, or lift the type filter." : "Select a name in the paper, capture what the story knows, then accept it into canon."}</p></div>
			) : (
				<div className="wiki-peek-list">
					{visible.slice(0, 60).map((entity) => {
						const entry = TYPE_META[entity.entity_type] ?? TYPE_META.other;
						return (
							<button className={`wiki-peek-row tone-${entry.tone}`} key={entity.id} onClick={() => setSelectedId(entity.id)}>
								<span className="wiki-peek-glyph" aria-hidden="true">{entry.glyph}</span>
								<span className="wiki-peek-copy">
									<span className="wiki-peek-name">{entity.name}</span>
									<small>{entry.label}{entity.aliases.length ? ` · ${entity.aliases.slice(0, 2).map((alias) => alias.alias).join(", ")}` : ""}</small>
								</span>
								<span className="wiki-peek-chevron" aria-hidden="true">›</span>
							</button>
						);
					})}
				</div>
			)}
		</div>
	);
}