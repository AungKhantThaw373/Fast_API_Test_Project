"use client";

import { useMemo } from "react";

import { ProvenanceChip } from "@/components/wiki/provenance-chip";
import { useEntityFacts } from "@/components/wiki/use-wiki";
import { capitalise } from "@/components/wiki/wiki-filters";
import type { EntityFact, FactStatus } from "@/lib/api";

export interface FactGroup {
	predicate: string;
	facts: EntityFact[];
	/** More than one accepted, or values that disagree: the writer must choose. */
	conflict: boolean;
}

export function groupFacts(facts: EntityFact[]): FactGroup[] {
	const byPredicate = new Map<string, EntityFact[]>();
	for (const fact of facts) {
		const list = byPredicate.get(fact.predicate) ?? [];
		list.push(fact);
		byPredicate.set(fact.predicate, list);
	}
	return [...byPredicate.entries()]
		.map(([predicate, group]) => {
			const live = group.filter((fact) => fact.status === "accepted");
			const values = new Set(live.map((fact) => factValue(fact)));
			return {
				predicate,
				facts: group.sort((a, b) => statusRank(a.status) - statusRank(b.status) || b.confidence - a.confidence),
				conflict: values.size > 1,
			};
		})
		.sort((a, b) => a.predicate.localeCompare(b.predicate));
}

function statusRank(status: FactStatus): number {
	return { proposed: 0, accepted: 1, superseded: 2, rejected: 3 }[status];
}

export function factValue(fact: EntityFact, entityNames?: Map<string, string>): string {
	if (fact.value_text) return fact.value_text;
	if (fact.value_number !== null) return String(fact.value_number);
	if (fact.value_date) return fact.value_date;
	if (fact.value_entity_id) return entityNames?.get(fact.value_entity_id) ?? fact.value_entity_id;
	return "—";
}

export function FactSection({
	storyId,
	entityId,
	onAdd,
	onEdit,
	onAccept,
	onReject,
	busyId,
	entityNames,
}: {
	storyId: string;
	entityId: string;
	entityNames?: Map<string, string>;
	onAdd: () => void;
	onEdit: (fact: EntityFact) => void;
	onAccept: (fact: EntityFact) => void;
	onReject: (fact: EntityFact) => void;
	busyId: string;
}) {
	const facts = useEntityFacts(entityId);
	const groups = useMemo(() => groupFacts(facts.data ?? []), [facts.data]);
	const proposed = (facts.data ?? []).filter((fact) => fact.status === "proposed").length;

	return (
		<section className="wiki-detail-section" aria-labelledby="facts-heading">
			<header className="wiki-section-head">
				<h2 id="facts-heading">Facts</h2>
				<div className="wiki-section-actions">
					{proposed > 0 && <span className="wiki-pending-chip">{proposed} proposed</span>}
					<button className="text-button" onClick={onAdd}>
						Add fact
					</button>
				</div>
			</header>
			{facts.isPending ? (
				<p className="wiki-quiet">Loading facts…</p>
			) : groups.length === 0 ? (
				<p className="wiki-quiet">No facts yet. A fact is one thing you know, with the sentence that proves it.</p>
			) : (
				<div className="fact-groups">
					{groups.map((group) => (
						<article className={`fact-group${group.conflict ? " has-conflict" : ""}`} key={group.predicate}>
							<div className="fact-group-head">
								<strong>{capitalise(group.predicate.replace(/_/g, " "))}</strong>
								{group.conflict && <span className="fact-conflict-flag">Which is canon?</span>}
							</div>
							{group.facts.map((fact) => (
								<div className={`fact-row status-${fact.status}`} key={fact.id}>
									<div className="fact-row-main">
										<p className="fact-value">{factValue(fact, entityNames)}</p>
										<div className="fact-meta">
											<ProvenanceChip
												storyId={storyId}
												chapterId={fact.chapter_id}
												chapterNumber={fact.valid_from_chapter}
												line={fact.line_start}
												quote={fact.quote}
											/>
											<span className={`fact-status status-${fact.status}`}>{fact.status}</span>
											<span>{fact.confidence}%</span>
											{fact.valid_from_chapter && <span>from ch. {fact.valid_from_chapter}</span>}
											{fact.valid_to_chapter && <span>to ch. {fact.valid_to_chapter}</span>}
											<span>{fact.created_by === "ai" ? "found by AI" : "added by you"}</span>
										</div>
									</div>
									<div className="fact-actions">
										{fact.status !== "accepted" && (
											<button className="text-button" disabled={busyId === fact.id} onClick={() => onAccept(fact)}>
												Accept
											</button>
										)}
										{fact.status !== "rejected" && (
											<button className="text-button subtle" disabled={busyId === fact.id} onClick={() => onReject(fact)}>
												Reject
											</button>
										)}
										<button className="text-button subtle" onClick={() => onEdit(fact)}>
											Edit
										</button>
									</div>
								</div>
							))}
						</article>
					))}
				</div>
			)}
		</section>
	);
}
