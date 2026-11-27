import { isAuthEndpoint, redirectToLogin } from "./auth-redirect";

const API_BASE_URL = "/api/py";

export interface ConflictDetails {
	currentRevision: number;
	currentTitle: string;
	currentContent: string;
	updatedAt: string;
}

export class ApiRequestError extends Error {
	constructor(
		message: string,
		readonly status: number,
		readonly retryAfterSeconds?: number,
		readonly conflict?: ConflictDetails,
	) {
		super(message);
		this.name = "ApiRequestError";
	}
}

export interface CurrentUser {
	id: string;
	username: string;
	email: string;
	created_at: string;
}

export interface AuthSession {
	id: string;
	user_agent: string;
	ip: string;
	created_at: string;
	last_seen_at: string;
	current: boolean;
}

export interface AuditEvent {
	id: string;
	action: string;
	target_type: string;
	target_id: string;
	detail: Record<string, unknown>;
	ip: string;
	created_at: string;
}

export interface Diagnostics {
	generated_at: string;
	database: string;
	database_size_bytes: number;
	pgvector: string;
	schema_status: string;
	worker: string;
	ollama: string;
	jobs: { queued: number; running: number; succeeded: number; failed: number; dead: number };
	ai_provider: string;
	ai_model: string;
	ai_usage_30d: { purpose: string; calls: number; input_tokens: number; output_tokens: number; cost_estimate: number }[];
	last_backup: { filename: string; size_bytes: number; modified_at: string } | null;
	slow_query_ms: number;
}

export interface StorageReport {
	generated_at: string;
	database_size_bytes: number;
	tables: { name: string; size_bytes: number }[];
	counts: {
		stories: number;
		chapters: number;
		chunks: number;
		revisions: number;
		jobs: number;
		trashed_stories: number;
		trashed_chapters: number;
	};
	expired: {
		trash_cutoff: string;
		jobs_cutoff: string;
		stories: number;
		chapters: number;
		jobs: number;
	};
	trash_retention_days: number;
	finished_jobs_retention_days: number;
}

export interface StorageCleanupResult {
	stories_deleted: number;
	chapters_deleted: number;
	jobs_deleted: number;
}

export interface AIProviderPreset {
	id: string;
	label: string;
	base_url: string;
}

export interface AISettings {
	provider: string | null;
	model: string | null;
	base_url: string | null;
	api_key_configured: boolean;
	using_server_default: boolean;
}

export interface Story {
	id: string;
	title: string;
	collection_name: string;
	scan_interval_words: number;
	external_analysis_enabled: boolean;
	chapter_count?: number;
	word_count?: number;
	chapter_warning_at?: number;
	created_at: string;
	updated_at: string;
}

export interface AIUsagePurpose {
	purpose: string;
	provider: string;
	model: string;
	calls: number;
	input_tokens: number;
	output_tokens: number;
	cost_usd: number;
	average_duration_ms: number;
}

export interface ScanJob {
	job_id: string;
}

export interface AskCitation {
	chunk_id: string;
	chapter_number: number;
	line: number;
	quote: string;
	explanation: string;
}

export interface AskStoryResponse {
	answer: string;
	unsure: boolean;
	citations: AskCitation[];
}

export interface AIUsage {
	month: string;
	calls: number;
	input_tokens: number;
	output_tokens: number;
	spent_usd: number;
	by_purpose: AIUsagePurpose[];
}

export interface Chapter {
	id: string;
	story_id: string;
	chapter_number: number;
	arc_id?: string | null;
	title: string;
	content?: string;
	word_count: number;
	revision: number;
	bible_scan_revision: number | null;
	bible_scan_error: string | null;
	index_status: "pending" | "indexing" | "indexed" | "failed";
	index_error: string | null;
	updated_at: string;
	deleted_at?: string | null;
}

export interface ChapterSynopsis {
	chapter_id: string;
	synopsis: string;
	editable: boolean;
	generated: boolean;
}

export interface RecapCitation {
	chapter_id: string;
	chapter_number: number;
	chapter_title: string;
	quote: string;
	line: number;
}

export interface RecapChapter {
	chapter_id: string;
	chapter_number: number;
	title: string;
	synopsis: string;
	citation: RecapCitation;
}

export interface RecapArc {
	arc_id: string;
	name: string;
	summary: string;
}

export interface StorySoFar {
	story_id: string;
	range_label: string;
	chapters: RecapChapter[];
	arcs: RecapArc[];
	read_only: boolean;
	generated_at: string;
}

export interface StoryArc {
	id: string;
	story_id: string;
	name: string;
	summary: string;
	position: number;
	chapter_count: number;
	first_chapter_number: number | null;
	last_chapter_number: number | null;
}

export interface ArcCoverage {
	arc_id: string;
	arc_name: string;
	position: number;
	chapter_count: number;
	first_chapter_number: number | null;
	last_chapter_number: number | null;
	extracted_count: number;
	pending_count: number;
	complete: boolean;
}

export interface CanonCoverage {
	story_id: string;
	current_arc_id: string | null;
	chapters: number;
	extracted: number;
	pending: number;
	unassigned_chapters: number;
	arcs: ArcCoverage[];
}

export interface ArcExtractResult {
	arc_id: string;
	scheduled_count: number;
	skipped_count: number;
	chapter_count: number;
}

export interface StoryDetails extends Story {
	chapters: Chapter[];
}

export interface StorySearchEntity {
	id: string;
	name: string;
	entity_type: string;
}

export interface StorySearchHit {
	chunk_id: string;
	chapter_id: string;
	chapter_number: number;
	chapter_title: string;
	scene_index: number;
	chunk_index: number;
	start_line: number;
	end_line: number;
	quote: string;
	score: number;
	scores: Record<string, number>;
	entities: StorySearchEntity[];
}

export interface StorySearchResponse {
	query: string;
	semantic_query: string;
	lexical_query: string;
	name_query: string;
	entity_ids: string[];
	cache_hit: boolean;
	timings_ms: Record<string, number>;
	results: StorySearchHit[];
}

export interface BibleEntry {
	id: string;
	category: "character" | "location" | "item" | "world_rule" | "worldbuilding" | "power_system" | "plot_thread";
	name: string;
	description: string;
	status: "suggested" | "accepted" | "dismissed";
	thread_state: "open" | "resolved" | null;
	confidence: number;
	source_chapter_id: string | null;
	source_quote: string | null;
	details: Record<string, unknown>;
	updated_at: string;
}

export interface ContinuityFinding {
	id: string;
	draft_quote: string;
	draft_line: number;
	earlier_quote: string;
	earlier_chapter_id: string | null;
	earlier_chapter_number: number;
	earlier_chapter_title: string;
	explanation: string;
	confidence: number;
	intentional: boolean;
	review_status: "open" | "resolved" | "dismissed";
}

export interface ChapterRevisionSummary {
	revision_number: number;
	title: string;
	word_count: number;
	kind: "autosave" | "checkpoint" | "restore";
	char_count: number;
	created_at: string;
}

export interface DiffHunk {
	old_start: number;
	old_lines: number;
	new_start: number;
	new_lines: number;
	lines: string[];
}

export interface RevisionDiff {
	older: Pick<ChapterRevisionSummary, "revision_number" | "word_count" | "kind" | "created_at">;
	newer: Pick<ChapterRevisionSummary, "revision_number" | "word_count" | "kind" | "created_at">;
	hunks: DiffHunk[];
}

export interface TrashedChapter {
	id: string;
	story_id: string;
	story_title: string;
	chapter_number: number;
	title: string;
	word_count: number;
	deleted_at: string | null;
}

export interface TrashedStory {
	id: string;
	title: string;
	chapter_count: number;
	deleted_at: string | null;
}

export interface TrashListing {
	retention_days: number;
	stories: TrashedStory[];
	chapters: TrashedChapter[];
}

export interface SystemStatus {
	database: string;
	pgvector: string;
	schema: string;
	ollama: string;
	pending_chapters: number;
	failed_chapters: number;
	running_jobs: number;
	queued_jobs: number;
	dead_jobs: number;
	/** "running" when a worker heartbeat is fresh, otherwise "offline". */
	worker: string;
}

export interface JobStatus {
	id: string;
	type: string;
	status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "dead";
	attempts: number;
	max_attempts: number;
	progress: {
		stage?: string;
		scenes_done?: number;
		scenes_total?: number;
		scenes_failed?: number;
		findings?: number;
		cancel_requested?: boolean;
		[key: string]: unknown;
	};
	last_error: string | null;
	run_at: string;
	created_at: string;
	updated_at: string;
}

export interface ChapterScan {
	scan: { id: string; chapter_revision: number; chapter_word_count: number; scenes_failed?: number; created_at: string } | null;
	findings: ContinuityFinding[];
}

export type EntityType =
	| "character"
	| "location"
	| "item"
	| "organization"
	| "concept"
	| "world_rule"
	| "power_system"
	| "creature"
	| "other"
	// A novel can name its own kind of entry. The built-ins stay first for
	// autocomplete; the API stores any lowercase slug (max 32 characters).
	| (string & {});

export type FactStatus = "proposed" | "accepted" | "rejected" | "superseded";
export type FactValueType = "text" | "number" | "date" | "entity" | "boolean";

export interface EntityAlias {
	id: string;
	alias: string;
	normalized_alias: string;
	alias_type: "name" | "title" | "epithet" | "disguise" | "translation" | "other";
}

export interface WikiEntity {
	id: string;
	story_id: string;
	entity_type: EntityType;
	name: string;
	summary: string;
	status: "active" | "merged" | "archived";
	merged_into_id: string | null;
	first_chapter_number: number | null;
	last_chapter_number: number | null;
	created_at: string;
	updated_at: string;
	aliases: EntityAlias[];
}

export interface EntityFact {
	id: string;
	entity_id: string;
	predicate: string;
	value_text: string | null;
	value_number: number | null;
	value_date: string | null;
	value_entity_id: string | null;
	value_type: FactValueType;
	chapter_id: string | null;
	scene_index: number | null;
	line_start: number | null;
	line_end: number | null;
	quote: string | null;
	confidence: number;
	status: FactStatus;
	valid_from_chapter: number | null;
	valid_to_chapter: number | null;
	supersedes_id: string | null;
	context: Record<string, unknown>;
	created_by: "human" | "ai";
	created_at: string;
	updated_at: string;
}

export interface EntityRelationship {
	id: string;
	story_id: string;
	from_entity_id: string;
	to_entity_id: string;
	relationship_type: string;
	description: string;
	since_chapter: number | null;
	until_chapter: number | null;
	chapter_id: string | null;
	quote: string | null;
	status: string;
	created_at: string;
	updated_at: string;
}

export interface EntityAppearance {
	chapter_id: string;
	chapter_number: number;
	chapter_title: string;
	line_start: number;
	line_end: number;
	quote: string;
}

export interface WikiThread {
	id: string;
	story_id: string;
	title: string;
	description: string;
	setup_chapter_id: string | null;
	setup_quote: string | null;
	payoff_chapter_id: string | null;
	state: "open" | "touched" | "resolved" | "abandoned";
	linked_entity_ids: string[];
	linked_entities: { id: string; name: string; entity_type: string }[];
	setup_chapter_number: number | null;
	setup_chapter_title: string | null;
	payoff_chapter_number: number | null;
	payoff_chapter_title: string | null;
	last_mention: {
		chapter_id: string;
		chapter_number: number;
		chapter_title: string;
		line: number;
		quote: string;
	} | null;
	created_at: string;
	updated_at: string;
}

export interface WikiEvent {
	id: string;
	story_id: string;
	chapter_id: string;
	scene_index: number | null;
	timeline_order: number | null;
	summary: string;
	location_entity_id: string | null;
	participant_entity_ids: string[];
	quote: string | null;
	created_at: string;
	updated_at: string;
}

export interface InboxSource {
	chapter_id: string | null;
	chapter_number: number | null;
	line: number | null;
	quote: string | null;
}

export interface InboxItem {
	id: string;
	kind: "fact" | "merge" | "finding";
	title: string;
	summary: string;
	confidence: number;
	source: InboxSource;
	actions: string[];
	why_held: string | null;
	entity_id: string | null;
	chapter_id: string | null;
}

export interface CanonException {
	id: string;
	story_id: string;
	scope: "pattern" | "entity" | "predicate";
	entity_id: string | null;
	predicate: string | null;
	pattern: string | null;
	reason: string;
	created_by: string;
	created_at: string;
}

export interface NameCandidate {
	name: string;
	count: number;
	first_line: number;
	sample: string;
}

export interface FactInput {
	predicate: string;
	value_text?: string | null;
	value_number?: number | null;
	value_date?: string | null;
	value_entity_id?: string | null;
	value_type?: FactValueType;
	chapter_id?: string | null;
	scene_index?: number | null;
	line_start?: number | null;
	line_end?: number | null;
	quote?: string | null;
	confidence?: number;
	status?: FactStatus;
	valid_from_chapter?: number | null;
	valid_to_chapter?: number | null;
	supersedes_id?: string | null;
	context?: Record<string, unknown>;
}

async function download(path: string): Promise<{ blob: Blob; filename: string }> {
	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include", cache: "no-store" });
	} catch {
		throw new ApiRequestError("Could not reach the server. Check that the backend is running, then try again.", 0);
	}
	if (!response.ok) {
		if (response.status === 401) redirectToLogin();
		const body = await response.json().catch(() => null);
		throw new ApiRequestError(typeof body?.detail === "string" ? body.detail : "That file could not be prepared.", response.status);
	}
	const disposition = response.headers.get("Content-Disposition") ?? "";
	const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
	const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
	return {
		blob: await response.blob(),
		filename: encoded ? decodeURIComponent(encoded) : plain || "manuscript",
	};
}

function readCookie(name: string): string | undefined {
	if (typeof document === "undefined") return undefined;
	const match = document.cookie.split("; ").find((item) => item.startsWith(`${name}=`));
	return match ? decodeURIComponent(match.slice(name.length + 1)) : undefined;
}

/** Fetch a CSRF cookie when the page has not loaded another API resource yet. */
export async function ensureCsrf(): Promise<void> {
	if (readCookie("csrf")) return;
	try {
		await fetch(`${API_BASE_URL}/health`, { credentials: "include", cache: "no-store" });
	} catch {
		// The form's submit error will explain an unreachable backend.
	}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const headers = new Headers(init?.headers);
	const method = (init?.method ?? "GET").toUpperCase();
	if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !headers.has("X-CSRF-Token")) {
		const token = readCookie("csrf");
		if (token) headers.set("X-CSRF-Token", token);
	}
	if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
		headers.set("Content-Type", "application/json");
	}
	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${path}`, {
			...init,
			credentials: "include",
			cache: "no-store",
			headers,
		});
	} catch {
		throw new ApiRequestError("Could not reach the server. Check that the backend is running, then try again.", 0);
	}
	if (!response.ok) {
		if (response.status === 401 && !isAuthEndpoint(path)) redirectToLogin();
		const body = await response.json().catch(() => null);
		const retryAfterValue = response.headers.get("Retry-After");
		const retryAfterSeconds = retryAfterValue && /^\d+(\.\d+)?$/.test(retryAfterValue) ? Math.ceil(Number(retryAfterValue)) : undefined;
		// A structured 409 body arrives as sibling keys next to `detail`.
		const detail = typeof body?.detail === "string" ? body.detail : undefined;
		const conflict = typeof body?.current_revision === "number"
			? {
				currentRevision: body.current_revision as number,
				currentTitle: String(body.current_title ?? ""),
				currentContent: String(body.current_content ?? ""),
				updatedAt: String(body.updated_at ?? ""),
			}
			: undefined;
		throw new ApiRequestError(detail ?? "Request failed", response.status, retryAfterSeconds, conflict);
	}
	if (response.status === 204) return undefined as T;
	return response.json() as Promise<T>;
}

export type BackupDocument = Record<string, unknown>;

export const api = {
	me: () => request<CurrentUser>("/me"),
	login: (email: string, password: string) => {
		const body = new URLSearchParams({ username: email, password });
		return request<{ message: string }>("/token", {
			method: "POST",
			headers: { "Content-Type": "application/x-www-form-urlencoded" },
			body,
		});
	},
	register: (username: string, email: string, password: string) =>
		request<{ id: string; username: string; email: string }>("/register", {
			method: "POST",
			body: JSON.stringify({ username, email, password }),
		}),
	logout: () => request<{ message: string }>("/logout", { method: "POST" }),
	forgotPassword: (email: string) => request<{ message: string }>("/forgot-password", {
		method: "POST",
		body: JSON.stringify({ email }),
	}),
	resetPassword: (token: string, newPassword: string) => request<{ message: string }>("/reset-password", {
		method: "POST",
		body: JSON.stringify({ token, new_password: newPassword }),
	}),
	changePassword: (currentPassword: string, newPassword: string) => request<{ message: string }>("/account/password", {
		method: "POST",
		body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
	}),
	sessions: async () => (await request<{ sessions: AuthSession[] }>("/sessions")).sessions,
	revokeSession: (sessionId: string) => request<{ message: string }>(`/sessions/${sessionId}`, { method: "DELETE" }),
	revokeAllSessions: () => request<{ message: string }>("/sessions/revoke-all", { method: "POST" }),
	auditEvents: async () => (await request<{ events: AuditEvent[] }>("/account/audit?limit=20")).events,
	accountExportUrl: "/api/py/account/export",
	deleteAccount: (password: string, confirmation: string) => request<{ message: string }>("/account", {
		method: "DELETE",
		body: JSON.stringify({ password, confirmation }),
	}),
	diagnostics: () => request<Diagnostics>("/system/diagnostics"),
	storage: () => request<StorageReport>("/system/storage"),
	cleanupStorage: () => request<StorageCleanupResult>("/system/storage/cleanup", { method: "POST" }),
	aiProviders: async () => (await request<{ providers: AIProviderPreset[] }>("/ai-providers")).providers,
	aiSettings: () => request<AISettings>("/ai-settings"),
	saveAISettings: (settings: { provider: string; model: string; api_key?: string; base_url?: string }) =>
		request<AISettings>("/ai-settings", { method: "PUT", body: JSON.stringify(settings) }),
	resetAISettings: () => request<AISettings>("/ai-settings", { method: "DELETE"}),
	stories: async () => {
		const stories: Story[] = [];
		let cursor: string | undefined;
		do {
			const page = await request<{ stories: Story[]; next_cursor?: string | null }>(
				`/stories?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
			);
			stories.push(...page.stories);
			cursor = page.next_cursor ?? undefined;
		} while (cursor);
		return stories;
	},
	createStory: (title: string) => request<Story>("/stories", {
		method: "POST",
		body: JSON.stringify({ title }),
	}),
	deleteStory: (storyId: string) => request<void>(`/stories/${storyId}`, { method: "DELETE" }),
	story: (storyId: string) => request<StoryDetails>(`/stories/${storyId}`),
	chapters: async (storyId: string) => {
		const story = await request<StoryDetails>(`/stories/${storyId}`);
		return story.chapters;
	},
	storyIndexStatus: (storyId: string) => request<{ chapters: Array<Pick<Chapter, "id" | "revision" | "word_count" | "index_status" | "index_error" | "bible_scan_revision" | "bible_scan_error">>; worker_alive: boolean }>(`/stories/${storyId}/index-status`),
	updateStory: (storyId: string, changes: Partial<Pick<Story, "title" | "collection_name" | "scan_interval_words" | "external_analysis_enabled">>) =>
		request<Story>(`/stories/${storyId}`, { method: "PATCH", body: JSON.stringify(changes) }),
	aiUsage: (storyId: string) => request<AIUsage>(`/stories/${storyId}/ai-usage`),
	askStory: (storyId: string, question: string) => request<AskStoryResponse>(`/stories/${storyId}/ask`, { method: "POST", body: JSON.stringify({ question }) }),
	queueScan: (chapterId: string, force = false) => request<ScanJob>(`/stories/chapters/${chapterId}/scan-job?force=${force}`, { method: "POST" }),
	cancelJob: (jobId: string) => request<JobStatus>(`/jobs/${jobId}/cancel`, { method: "POST" }),
	createChapter: (storyId: string, title = "Untitled chapter", content = "") =>
		request<Chapter>(`/stories/${storyId}/chapters`, {
			method: "POST",
			body: JSON.stringify({ title, content }),
		}),
	deleteChapter: (chapterId: string) => request<{ chapters: Chapter[] }>(`/stories/chapters/${chapterId}`, { method: "DELETE" }),
	reorderChapters: (storyId: string, chapterIds: string[]) => request<{ chapters: Chapter[] }>(`/stories/${storyId}/chapters/order`, { method: "PUT", body: JSON.stringify({ chapter_ids: chapterIds }) }),
	moveChapter: (chapterId: string, destinationStoryId: string) => request<{ story_id: string; chapter: Chapter }>(`/stories/chapters/${chapterId}/move`, { method: "POST", body: JSON.stringify({ destination_story_id: destinationStoryId }) }),
	chapter: (chapterId: string) => request<Chapter>(`/stories/chapters/${chapterId}`),
	updateChapter: (chapterId: string, title: string, content: string, expectedRevision: number, clientSaveId?: string) =>
		request<Chapter>(`/stories/chapters/${chapterId}`, {
			method: "PUT",
			body: JSON.stringify({ title, content, expected_revision: expectedRevision, client_save_id: clientSaveId }),
		}),
	checkpointChapter: (chapterId: string, label?: string) =>
		request<{ revision_number: number; kind: string; word_count: number; created_at: string }>(`/stories/chapters/${chapterId}/checkpoint`, {
			method: "POST",
			body: JSON.stringify({ label }),
		}),
	diffRevisions: (chapterId: string, older: number, newer: number) =>
		request<RevisionDiff>(`/stories/chapters/${chapterId}/revisions/${older}/diff/${newer}`),
	trash: () => request<TrashListing>("/trash"),
	restoreTrashChapter: (chapterId: string) => request<{ chapter: Pick<Chapter, "id" | "story_id" | "chapter_number" | "title">; renumbered_from: number | null }>(`/trash/chapters/${chapterId}/restore`, { method: "POST" }),
	restoreTrashStory: (storyId: string) => request<{ story_id: string; restored_chapters: number }>(`/trash/stories/${storyId}/restore`, { method: "POST" }),
	deleteTrashChapter: (chapterId: string) => request<void>(`/trash/chapters/${chapterId}`, { method: "DELETE" }),
	deleteTrashStory: (storyId: string) => request<void>(`/trash/stories/${storyId}`, { method: "DELETE" }),
	systemStatus: () => request<SystemStatus>("/system/status"),
	job: (jobId: string) => request<JobStatus>(`/jobs/${jobId}`),
	chapterRevisions: async (chapterId: string) => (await request<{ revisions: ChapterRevisionSummary[] }>(`/stories/chapters/${chapterId}/revisions`)).revisions,
	restoreChapterRevision: (chapterId: string, revisionNumber: number) => request<Chapter>(`/stories/chapters/${chapterId}/revisions/${revisionNumber}/restore`, { method: "POST" }),
	chapterStatus: (chapterId: string) => request<Pick<Chapter, "id" | "revision" | "word_count" | "index_status" | "index_error" | "bible_scan_revision" | "bible_scan_error">>(`/stories/chapters/${chapterId}/status`),
	retryChapterIndex: (chapterId: string) => request<{ id: string; index_status: string }>(`/stories/chapters/${chapterId}/reindex`, { method: "POST" }),
	importManuscript: (storyId: string, filename: string, content: string) =>
		request<{ chapters: Chapter[] }>(`/stories/${storyId}/import`, {
			method: "POST",
			body: JSON.stringify({ filename, content }),
		}),
	bible: async (storyId: string) => {
		const entries: BibleEntry[] = [];
		let cursor: string | undefined;
		do {
			const page = await request<{ entries: BibleEntry[]; next_cursor?: string | null }>(
				`/stories/${storyId}/bible?limit=500${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
			);
			entries.push(...page.entries);
			cursor = page.next_cursor ?? undefined;
		} while (cursor);
		return entries;
	},
	createBibleEntry: (storyId: string, entry: Pick<BibleEntry, "category" | "name" | "description" | "details">) => request<BibleEntry>(`/stories/${storyId}/bible`, { method: "POST", body: JSON.stringify(entry) }),
	scanBibleRange: (storyId: string, startChapter: number, endChapter: number, force = false) =>
		request<{ scheduled_count: number; skipped_count: number; scheduled_chapters: Array<{ id: string; revision: number }> }>(`/stories/${storyId}/bible/scan`, {
			method: "POST",
			body: JSON.stringify({ start_chapter: startChapter, end_chapter: endChapter, force }),
		}),
	decideBibleEntry: (entryId: string, decision: "accepted" | "dismissed") =>
		request<BibleEntry>(`/stories/bible/${entryId}/decision`, {
			method: "PATCH",
			body: JSON.stringify({ status: decision }),
		}),
	editBibleEntry: (entryId: string, changes: Pick<BibleEntry, "category" | "name" | "description" | "details">) => request<BibleEntry>(`/stories/bible/${entryId}`, { method: "PUT", body: JSON.stringify(changes) }),
	deleteBibleEntry: (entryId: string) => request<void>(`/stories/bible/${entryId}`, { method: "DELETE" }),
	updateThread: (entryId: string, state: "open" | "resolved") =>
		request<BibleEntry>(`/stories/bible/${entryId}/thread`, {
			method: "PATCH",
			body: JSON.stringify({ thread_state: state }),
		}),
	latestScan: async (chapterId: string) => {
		const first = await request<ChapterScan & { next_cursor?: string | null }>(
			`/stories/chapters/${chapterId}/scan`,
		);
		let cursor = first.next_cursor ?? undefined;
		if (!cursor) return first;
		const findings = [...first.findings];
		while (cursor) {
			const page: ChapterScan & { next_cursor?: string | null } = await request(
				`/stories/chapters/${chapterId}/scan?cursor=${encodeURIComponent(cursor)}`,
			);
			findings.push(...page.findings);
			cursor = page.next_cursor ?? undefined;
		}
		return { scan: first.scan, findings };
	},
	scanChapter: (chapterId: string, force = false) => request<{ scan_id: string; finding_count: number; chapter_revision: number; reused: boolean }>(
		`/stories/chapters/${chapterId}/scan${force ? "?force=true" : ""}`, { method: "POST" },
	),
	markIntentional: (findingId: string, intentional = true) =>
		request<{ id: string; intentional: boolean }>(`/stories/findings/${findingId}/intentional`, {
			method: "PATCH",
			body: JSON.stringify({ intentional }),
		}),
	reviewFinding: (findingId: string, reviewStatus: "open" | "resolved" | "dismissed") => request<{ id: string; review_status: ContinuityFinding["review_status"]; intentional: boolean }>(`/stories/findings/${findingId}/review`, { method: "PATCH", body: JSON.stringify({ review_status: reviewStatus }) }),
	entities: async (
		storyId: string,
		filters: { type?: string; status?: string; q?: string; arc_id?: string; limit?: number } = {},
	) => {
		const entities: WikiEntity[] = [];
		let cursor: string | undefined;
		do {
			const params = new URLSearchParams({ limit: String(filters.limit ?? 200) });
			if (filters.type) params.set("type", filters.type);
			if (filters.status) params.set("status", filters.status);
			if (filters.q) params.set("q", filters.q);
			if (filters.arc_id) params.set("arc_id", filters.arc_id);
			if (cursor) params.set("cursor", cursor);
			const page = await request<{ entities: WikiEntity[]; next_cursor?: string | null }>(
				`/stories/${storyId}/entities?${params.toString()}`,
			);
			entities.push(...page.entities);
			cursor = page.next_cursor ?? undefined;
		} while (cursor);
		return entities;
	},
	searchStory: (
		storyId: string,
		params: {
			q: string;
			limit?: number;
			chapterMin?: number;
			chapterMax?: number;
			entityId?: string;
			arcId?: string;
			chunkKind?: string;
		},
		signal?: AbortSignal,
	) => {
		const search = new URLSearchParams({ q: params.q, limit: String(params.limit ?? 20) });
		if (params.chapterMin) search.set("chapter_min", String(params.chapterMin));
		if (params.chapterMax) search.set("chapter_max", String(params.chapterMax));
		if (params.entityId) search.set("entity_id", params.entityId);
		if (params.arcId) search.set("arc_id", params.arcId);
		if (params.chunkKind) search.set("chunk_kind", params.chunkKind);
		return request<StorySearchResponse>(`/stories/${storyId}/search?${search.toString()}`, { signal });
	},
	searchEntities: async (storyId: string, q: string) =>
		(await request<{ entities: WikiEntity[] }>(
			`/entities/search?story_id=${storyId}&q=${encodeURIComponent(q)}`,
		)).entities,
	entity: (entityId: string) => request<WikiEntity>(`/entities/${entityId}`),
	createEntity: (
		storyId: string,
		input: { name: string; entity_type: EntityType; summary?: string; aliases?: Array<{ alias: string; alias_type?: string }> },
	) => request<WikiEntity>(`/stories/${storyId}/entities`, { method: "POST", body: JSON.stringify(input) }),
	updateEntity: (entityId: string, changes: { name?: string; entity_type?: EntityType; summary?: string }) =>
		request<WikiEntity>(`/entities/${entityId}`, { method: "PUT", body: JSON.stringify(changes) }),
	archiveEntity: (entityId: string) => request<void>(`/entities/${entityId}`, { method: "DELETE" }),
	addEntityAlias: (entityId: string, alias: string, aliasType = "name") =>
		request<EntityAlias>(`/entities/${entityId}/aliases`, {
			method: "POST",
			body: JSON.stringify({ alias, alias_type: aliasType }),
		}),
	deleteEntityAlias: (entityId: string, aliasId: string) =>
		request<void>(`/entities/${entityId}/aliases/${aliasId}`, { method: "DELETE" }),
	mergeEntity: (entityId: string, targetId: string, dryRun = false) =>
		request<{ source_id: string; target_id: string; dry_run: boolean; moved: Record<string, number> }>(
			`/entities/${entityId}/merge`,
			{ method: "POST", body: JSON.stringify({ target_id: targetId, dry_run: dryRun }) },
		),
	unmergeEntity: (entityId: string) =>
		request<{ source_id: string; target_id: string; merge_id: string; reverted_at: string | null }>(
			`/entities/${entityId}/unmerge`,
			{ method: "POST" },
		),
	entityAppearances: async (entityId: string, limit = 100) => {
		const appearances: EntityAppearance[] = [];
		let cursor: string | undefined;
		do {
			const params = new URLSearchParams({ limit: String(limit) });
			if (cursor) params.set("cursor", cursor);
			const page = await request<{ appearances: EntityAppearance[]; next_cursor?: string | null }>(
				`/entities/${entityId}/appearances?${params.toString()}`,
			);
			appearances.push(...page.appearances);
			cursor = page.next_cursor ?? undefined;
		} while (cursor);
		return appearances;
	},
	entityFacts: async (entityId: string, filters: { status?: string; predicate?: string } = {}) => {
		const params = new URLSearchParams();
		if (filters.status) params.set("status", filters.status);
		if (filters.predicate) params.set("predicate", filters.predicate);
		const query = params.toString();
		return (
			await request<{ facts: EntityFact[] }>(`/entities/${entityId}/facts${query ? `?${query}` : ""}`)
		).facts;
	},
	createFact: (entityId: string, input: FactInput) =>
		request<EntityFact>(`/entities/${entityId}/facts`, { method: "POST", body: JSON.stringify(input) }),
	updateFact: (factId: string, changes: Partial<FactInput>) =>
		request<EntityFact>(`/facts/${factId}`, { method: "PUT", body: JSON.stringify(changes) }),
	deleteFact: (factId: string) => request<void>(`/facts/${factId}`, { method: "DELETE" }),
	acceptFact: (factId: string) => request<EntityFact>(`/facts/${factId}/accept`, { method: "POST" }),
	rejectFact: (factId: string) => request<EntityFact>(`/facts/${factId}/reject`, { method: "POST" }),
	entityRelationships: (entityId: string) =>
		request<{ outgoing: EntityRelationship[]; incoming: EntityRelationship[] }>(
			`/entities/${entityId}/relationships`,
		),
	createRelationship: (
		entityId: string,
		input: {
			to_entity_id: string;
			relationship_type: string;
			description?: string;
			since_chapter?: number | null;
			chapter_id?: string | null;
			quote?: string | null;
		},
	) =>
		request<EntityRelationship>(`/entities/${entityId}/relationships`, {
			method: "POST",
			body: JSON.stringify(input),
		}),
	updateRelationship: (
		relationshipId: string,
		changes: {
			relationship_type?: string;
			description?: string;
			since_chapter?: number | null;
			until_chapter?: number | null;
		},
	) =>
		request<EntityRelationship>(`/relationships/${relationshipId}`, {
			method: "PATCH",
			body: JSON.stringify(changes),
		}),
	deleteRelationship: (relationshipId: string) =>
		request<void>(`/relationships/${relationshipId}`, { method: "DELETE" }),
	threads: async (storyId: string, state?: string) => {
		const query = state ? `?state=${state}` : "";
		return (await request<{ threads: WikiThread[] }>(`/stories/${storyId}/threads${query}`)).threads;
	},
	nameCandidates: async (storyId: string, chapterId: string) =>
		request<{ chapter_id: string; chapter_number: number; candidates: NameCandidate[] }>(
			`/stories/${storyId}/chapters/${chapterId}/name-candidates`,
		),
	acceptNameCandidate: (
		storyId: string,
		input: { name: string; entity_type: EntityType; chapter_id: string; line_start?: number | null; quote?: string | null },
	) => request<WikiEntity>(`/stories/${storyId}/name-candidates/accept`, { method: "POST", body: JSON.stringify(input) }),
	createThread: (
		storyId: string,
		input: {
			title: string;
			description?: string;
			setup_chapter_id?: string | null;
			setup_quote?: string | null;
			state?: string;
			linked_entity_ids?: string[];
		},
	) => request<WikiThread>(`/stories/${storyId}/threads`, { method: "POST", body: JSON.stringify(input) }),
	updateThreadEntry: (
		threadId: string,
		changes: {
			title?: string;
			description?: string;
			setup_chapter_id?: string | null;
			state?: string;
			payoff_chapter_id?: string | null;
			linked_entity_ids?: string[];
		},
	) => request<WikiThread>(`/threads/${threadId}`, { method: "PATCH", body: JSON.stringify(changes) }),
	deleteThreadEntry: (threadId: string) => request<void>(`/threads/${threadId}`, { method: "DELETE" }),
	events: async (storyId: string, chapterId?: string) => {
		const query = chapterId ? `?chapter_id=${chapterId}` : "";
		return (await request<{ events: WikiEvent[] }>(`/stories/${storyId}/events${query}`)).events;
	},
	createEvent: (
		storyId: string,
		input: {
			chapter_id: string;
			summary: string;
			scene_index?: number | null;
			timeline_order?: number | null;
			location_entity_id?: string | null;
			participant_entity_ids?: string[];
			quote?: string | null;
		},
	) => request<WikiEvent>(`/stories/${storyId}/events`, { method: "POST", body: JSON.stringify(input) }),
	inbox: async (
		storyId: string,
		filters: { kind?: string; status?: string; limit?: number; cursor?: string } = {},
	) => {
		const params = new URLSearchParams();
		if (filters.kind) params.set("kind", filters.kind);
		if (filters.status) params.set("status", filters.status);
		params.set("limit", String(filters.limit ?? 100));
		if (filters.cursor) params.set("cursor", filters.cursor);
		return request<{ items: InboxItem[]; next_cursor: string | null }>(
			`/stories/${storyId}/inbox?${params.toString()}`,
		);
	},
	exceptions: async (storyId: string) =>
		(await request<{ exceptions: CanonException[] }>(`/stories/${storyId}/exceptions`)).exceptions,
	createException: (
		storyId: string,
		input: {
			scope: string;
			reason: string;
			pattern?: string | null;
			entity_id?: string | null;
			predicate?: string | null;
		},
	) =>
		request<CanonException>(`/stories/${storyId}/exceptions`, {
			method: "POST",
			body: JSON.stringify(input),
		}),
	deleteException: (exceptionId: string) =>
		request<void>(`/exceptions/${exceptionId}`, { method: "DELETE" }),
	inboxDecide: (storyId: string, ids: string[], action: string) =>
		request<{ facts: number; findings: number; merges: number; skipped: number; action: string }>(
			`/stories/${storyId}/inbox/decide`,
			{ method: "POST", body: JSON.stringify({ ids, action }) },
		),
	autoAcceptRules: (storyId: string) =>
		request<{
			require_quote: boolean;
			min_confidence: number;
			require_existing_entity: boolean;
			block_conflicts: boolean;
			max_per_chapter: number;
		}>(`/stories/${storyId}/inbox/rules`),
	saveAutoAcceptRules: (
		storyId: string,
		rules: {
			require_quote?: boolean;
			min_confidence?: number;
			require_existing_entity?: boolean;
			block_conflicts?: boolean;
			max_per_chapter?: number;
		},
	) => request<Record<string, unknown>>(`/stories/${storyId}/inbox/rules`, { method: "PUT", body: JSON.stringify(rules) }),
	autoAcceptPreview: (storyId: string) =>
		request<{
			would_accept: number;
			held: number;
			total: number;
			rules: Record<string, unknown>;
		}>(`/stories/${storyId}/inbox/rules/preview`),
	runAutoAccept: (storyId: string) =>
		request<{ accepted: number; held: number }>(`/stories/${storyId}/inbox/auto-accept`, { method: "POST" }),
	mergeProposals: async (storyId: string) =>
		request<Array<{ id: string; source_id: string; target_id: string; source_name: string; target_name: string; score: number; status: string }>>(
			`/stories/${storyId}/merge-proposals`,
		),
	arcs: (storyId: string) => request<Array<StoryArc>>(`/stories/${storyId}/arcs`),
	canonCoverage: (storyId: string) => request<CanonCoverage>(`/stories/${storyId}/canon/coverage`),
	extractArc: (storyId: string, arcId: string, force = false) =>
		request<ArcExtractResult>(`/stories/${storyId}/canon/arcs/${arcId}/extract?force=${force}`, {
			method: "POST",
		}),
	createArc: (storyId: string, name: string, summary = "") =>
		request<StoryArc>(`/stories/${storyId}/arcs`, { method: "POST", body: JSON.stringify({ name, summary }) }),
	updateArc: (arcId: string, changes: { name?: string; summary?: string; position?: number }) =>
		request<StoryArc>(`/arcs/${arcId}`, { method: "PATCH", body: JSON.stringify(changes) }),
	deleteArc: (arcId: string) => request<void>(`/arcs/${arcId}`, { method: "DELETE" }),
	assignArc: (storyId: string, arcId: string | null, chapterIds: string[]) =>
		request<{ updated: number }>(`/stories/${storyId}/arcs`, {
			method: "PUT",
			body: JSON.stringify({ arc_id: arcId, chapter_ids: chapterIds }),
		}),
	chapterSynopsis: (chapterId: string) =>
		request<ChapterSynopsis>(`/stories/chapters/${chapterId}/synopsis`),
	updateChapterSynopsis: (chapterId: string, synopsis: string) =>
		request<ChapterSynopsis>(`/stories/chapters/${chapterId}/synopsis`, {
			method: "PUT",
			body: JSON.stringify({ synopsis }),
		}),
	generateChapterSynopsis: (chapterId: string, overwrite = false) =>
		request<ChapterSynopsis>(
			`/stories/chapters/${chapterId}/synopsis/generate${overwrite ? "?overwrite=true" : ""}`,
			{ method: "POST" },
		),
	generateArcSummary: (storyId: string, arcId: string) =>
		request<{ arc_id: string; summary: string; chapter_count: number }>(
			`/stories/${storyId}/arcs/${arcId}/summary/generate`,
			{ method: "POST" },
		),
	exportStory: (storyId: string, format: "markdown" | "docx" | "epub" | "pdf", includeWiki: boolean) =>
		download(`/stories/${storyId}/export?format=${format}&include_wiki=${includeWiki}`),
	exportBackup: (storyId: string) => request<BackupDocument>(`/stories/${storyId}/backup`),
	importBackup: (document: BackupDocument) =>
		request<{ story_id: string; chapters: number; entities: number; facts: number; relationships: number; threads: number; events: number }>("/stories/import-backup", {
			method: "POST",
			body: JSON.stringify(document),
		}),
	storySoFar: (storyId: string, limit = 5, arcId?: string) => {
		const params = new URLSearchParams({ limit: String(limit) });
		if (arcId) params.set("arc_id", arcId);
		return request<StorySoFar>(`/stories/${storyId}/recap?${params.toString()}`);
	},
};
