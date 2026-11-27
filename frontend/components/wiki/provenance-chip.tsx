"use client";

import Link from "next/link";

/** Where a fact came from, in one clickable chip. The trust mechanism. */
export function ProvenanceChip({
	storyId,
	chapterId,
	chapterNumber,
	line,
	quote,
}: {
	storyId: string;
	chapterId: string | null;
	chapterNumber: number | null;
	line: number | null;
	quote: string | null;
}) {
	const label = [
		chapterNumber ? `Ch. ${chapterNumber}` : chapterId ? "Chapter" : null,
		line ? `line ${line}` : null,
		quote ? `“${truncate(quote, 46)}”` : null,
	]
		.filter(Boolean)
		.join(" · ");

	if (!chapterId) return <span className="provenance-chip muted">{label || "No source"}</span>;

	const href = `/stories/${storyId}?chapter=${chapterId}${line ? `&line=${line}` : ""}`;
	return (
		<Link className="provenance-chip" href={href} title="Open this passage in the studio">
			{label || "Open source"}
		</Link>
	);
}

export function truncate(value: string, limit: number): string {
	const text = value.replace(/\s+/g, " ").trim();
	return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}
