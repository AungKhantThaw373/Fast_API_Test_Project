"use client";

import { useEffect, useMemo, useState } from "react";

import { capitalise, hasActiveFilters, toSearchParams, type WikiFilters } from "@/components/wiki/wiki-filters";
import type { WikiEntryType } from "@/lib/api";

const STORAGE_KEY = "stillroom:saved-views";

interface SavedView {
	name: string;
	filters: WikiFilters;
}

/** Views that are useful before anyone saves one. */
const TYPE_PRESETS: SavedView[] = [
	{ name: "Characters", filters: { type: "character", status: "", arc: "", q: "" } },
	{ name: "Places", filters: { type: "location", status: "", arc: "", q: "" } },
];
function presetsFor(types?: Pick<WikiEntryType, "key" | "label">[]): SavedView[] {
	if (!types?.length) return TYPE_PRESETS;
	const seen = new Set<string>();
	const typePresets: SavedView[] = [];
	for (const type of types) {
		if (seen.has(type.label)) continue;
		seen.add(type.label);
		typePresets.push({
			name: type.label,
			filters: { type: type.key, status: "", arc: "", q: "" },
		});
		if (typePresets.length === 2) break;
	}
	return typePresets;
}

function readViews(): SavedView[] {
	if (typeof window === "undefined") return [];
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY);
		if (!raw) return [];
		const parsed: unknown = JSON.parse(raw);
		if (!Array.isArray(parsed)) return [];
		return parsed.filter(
			(item): item is SavedView =>
				typeof item === "object" && item !== null && typeof (item as SavedView).name === "string",
		);
	} catch {
		return [];
	}
}

export function SavedViews({
	filters,
	onApply,
	types,
}: {
	filters: WikiFilters;
	onApply: (filters: WikiFilters) => void;
	types?: Pick<WikiEntryType, "key" | "label">[];
}) {
	const presets = useMemo(() => presetsFor(types), [types]);
	const [views, setViews] = useState<SavedView[]>([]);
	const [naming, setNaming] = useState(false);
	const [name, setName] = useState("");

	useEffect(() => {
		// Deferred so the server-rendered rail and the first client render agree.
		const frame = window.requestAnimationFrame(() => setViews(readViews()));
		return () => window.cancelAnimationFrame(frame);
	}, []);

	const persist = (next: SavedView[]) => {
		setViews(next);
		window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
	};

	const save = () => {
		const trimmed = name.trim();
		if (!trimmed) return;
		persist([...views.filter((view) => view.name !== trimmed), { name: trimmed, filters }]);
		setName("");
		setNaming(false);
	};

	const remove = (target: string) => persist(views.filter((view) => view.name !== target));

	return (
		<section className="saved-views" aria-labelledby="saved-views-heading">
			<div className="saved-views-head">
				<span id="saved-views-heading">SAVED VIEWS</span>
				<button className="text-button subtle" onClick={() => setNaming((value) => !value)}>
					{naming ? "Cancel" : "Save"}
				</button>
			</div>
			{naming && (
				<form
					className="saved-views-form"
					onSubmit={(event) => {
						event.preventDefault();
						save();
					}}
				>
					<input
						autoFocus
						value={name}
						onChange={(event) => setName(event.target.value)}
						placeholder="Name this view"
						aria-label="Saved view name"
						maxLength={60}
						onKeyDown={(event) => {
							if (event.key === "Escape") setNaming(false);
						}}
					/>
					<button className="text-button" type="submit">
						Add
					</button>
				</form>
			)}
			<p className="saved-views-hint">
				{hasActiveFilters(filters)
					? `Saving: ${toSearchParams(filters).replace("?", "").replaceAll("&", ", ").replaceAll("=", " ")}`
					: "Set some filters, then save them."}
			</p>
			<ul className="saved-views-list">
				{[...views, ...presets.filter((preset) => !views.some((view) => view.name === preset.name))].map((view) => (
					<li key={view.name}>
						<button className="saved-view-apply" onClick={() => onApply(view.filters)}>
							{capitalise(view.name)}
						</button>
						{views.some((saved) => saved.name === view.name) && (
							<button
								className="saved-view-remove"
								aria-label={`Forget ${view.name}`}
								onClick={() => remove(view.name)}
							>
								×
							</button>
						)}
					</li>
				))}
			</ul>
		</section>
	);
}
