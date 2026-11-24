/**
 * Query keys for the wiki surface.
 *
 * Keys are hierarchical so a mutation can invalidate a family: invalidating
 * `["entities", storyId]` refreshes every filtered list for that story without
 * touching chapter or inbox data.
 */
export interface EntityFilters {
	type?: string;
	status?: string;
	q?: string;
	arc_id?: string;
	limit?: number;
}

export const qk = {
	me: () => ["me"] as const,
	stories: () => ["stories"] as const,
	story: (id: string) => ["story", id] as const,
	chapters: (id: string) => ["story", id, "chapters"] as const,
	arcs: (id: string) => ["story", id, "arcs"] as const,
	chapter: (id: string) => ["chapter", id] as const,
	bible: (id: string) => ["story", id, "bible"] as const,
	entities: (storyId: string, filters: EntityFilters = {}) => ["entities", storyId, filters] as const,
	entityList: (storyId: string) => ["entities", storyId] as const,
	entity: (id: string) => ["entity", id] as const,
	entityFacts: (id: string) => ["entity", id, "facts"] as const,
	entityAppearances: (id: string) => ["entity", id, "appearances"] as const,
	entityRelationships: (id: string) => ["entity", id, "relationships"] as const,
	entitySearch: (storyId: string, q: string) => ["entities", storyId, "search", q] as const,
	threads: (storyId: string) => ["threads", storyId] as const,
	events: (storyId: string) => ["events", storyId] as const,
	inbox: (storyId: string) => ["inbox", storyId] as const,
	exceptions: (storyId: string) => ["exceptions", storyId] as const,
	nameCandidates: (chapterId: string) => ["name-candidates", chapterId] as const,
	scan: (chapterId: string) => ["scan", chapterId] as const,
	job: (id: string) => ["job", id] as const,
	status: () => ["system", "status"] as const,
};
