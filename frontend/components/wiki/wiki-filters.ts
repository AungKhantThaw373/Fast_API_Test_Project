import type { EntityAlias, EntityType, WikiEntity } from "@/lib/api";

export const ENTITY_TYPES: EntityType[] = [
	"character",
	"location",
	"item",
	"organization",
	"concept",
	"world_rule",
	"power_system",
	"creature",
	"other",
];

export const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
	character: "Character",
	location: "Place",
	item: "Item",
	organization: "Group",
	concept: "Concept",
	world_rule: "World rule",
	power_system: "Power system",
	creature: "Creature",
	other: "Other",
};

export function entityTypeLabel(value: string): string {
	return ENTITY_TYPE_LABELS[value] ?? capitalise(value.replace(/_/g, " "));
}

/** The API stores a short lowercase slug; spaces and punctuation become underscores. */
export function normalizeEntityType(value: string): string {
	const slug = value
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "_")
		.replace(/^_+|_+$/g, "")
		.slice(0, 32);
	if (!slug) return "other";
	return /^[a-z]/.test(slug) ? slug : `type_${slug}`.slice(0, 32);
}

export interface WikiFilters {
	type: string;
	status: string;
	arc: string;
	q: string;
}

export const EMPTY_FILTERS: WikiFilters = { type: "", status: "", arc: "", q: "" };

type RawParams = Record<string, string | string[] | undefined> | URLSearchParams;

function read(params: RawParams, key: string): string {
	if (params instanceof URLSearchParams) return params.get(key) ?? "";
	const value = params[key];
	if (Array.isArray(value)) return value[0] ?? "";
	return value ?? "";
}

export function parseFilters(params: RawParams): WikiFilters {
	return {
		type: read(params, "type"),
		status: read(params, "status"),
		arc: read(params, "arc"),
		q: read(params, "q"),
	};
}

export function toSearchParams(filters: WikiFilters): string {
	const params = new URLSearchParams();
	if (filters.type) params.set("type", filters.type);
	if (filters.status) params.set("status", filters.status);
	if (filters.arc) params.set("arc", filters.arc);
	if (filters.q.trim()) params.set("q", filters.q.trim());
	const query = params.toString();
	return query ? `?${query}` : "";
}

export function filtersForApi(filters: WikiFilters): {
	type?: string;
	status?: string;
	arc_id?: string;
	q?: string;
} {
	const apiFilters: { type?: string; status?: string; arc_id?: string; q?: string } = {};
	if (filters.type) apiFilters.type = filters.type;
	if (filters.status) apiFilters.status = filters.status;
	if (filters.arc) apiFilters.arc_id = filters.arc;
	if (filters.q.trim()) apiFilters.q = filters.q.trim();
	return apiFilters;
}

export function hasActiveFilters(filters: WikiFilters): boolean {
	return Boolean(filters.type || filters.status || filters.arc || filters.q.trim());
}

export function activeFilterLabels(filters: WikiFilters): string[] {
	const labels: string[] = [];
	if (filters.q.trim()) labels.push(`“${filters.q.trim()}”`);
	if (filters.type) labels.push(entityTypeLabel(filters.type));
	if (filters.status) labels.push(filters.status === "archived" ? "Archived" : capitalise(filters.status));
	return labels;
}

export function capitalise(value: string): string {
	return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

export function summariseAliases(aliases: EntityAlias[], max = 3): { shown: string[]; more: number } {
	const shown = aliases.slice(0, max).map((alias) => alias.alias);
	return { shown, more: Math.max(0, aliases.length - shown.length) };
}

export function oneLineSummary(entity: Pick<WikiEntity, "summary" | "name">, limit = 120): string {
	const text = entity.summary.trim() || `No summary yet for ${entity.name}.`;
	const single = text.replace(/\s+/g, " ");
	return single.length > limit ? `${single.slice(0, limit - 1).trimEnd()}…` : single;
}

export function lastSeenLabel(entity: Pick<WikiEntity, "last_chapter_number" | "first_chapter_number">): string {
	if (entity.last_chapter_number) return `Last seen ch. ${entity.last_chapter_number}`;
	if (entity.first_chapter_number) return `First seen ch. ${entity.first_chapter_number}`;
	return "Not yet mentioned";
}

export function openThreadCount(entityId: string, threads: Array<{ linked_entity_ids: string[]; state: string }>): number {
	return threads.filter(
		(thread) => thread.state !== "resolved" && thread.state !== "abandoned" && thread.linked_entity_ids.includes(entityId),
	).length;
}
