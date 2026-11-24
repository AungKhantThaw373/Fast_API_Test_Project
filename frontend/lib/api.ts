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
	created_at: string;
	updated_at: string;
}

export interface Chapter {
	id: string;
	story_id: string;
	chapter_number: number;
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

export interface StoryDetails extends Story {
	chapters: Chapter[];
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
	worker: string;
}

export interface ChapterScan {
	scan: { id: string; chapter_revision: number; chapter_word_count: number; created_at: string } | null;
	findings: ContinuityFinding[];
}

export interface DraftFolder {
	id: string;
	name: string;
	file_count: number;
	size_bytes: number;
	created_at: string;
	updated_at: string;
}

export interface DraftFile {
	id: string;
	folder_id: string;
	folder_name: string;
	title: string;
	original_filename: string;
	extension: string;
	media_type: string;
	size_bytes: number;
	sha256: string;
	created_at: string;
	updated_at: string;
	previewable: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const headers = new Headers(init?.headers);
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
	aiProviders: async () => (await request<{ providers: AIProviderPreset[] }>("/ai-providers")).providers,
	aiSettings: () => request<AISettings>("/ai-settings"),
	saveAISettings: (settings: { provider: string; model: string; api_key?: string; base_url?: string }) =>
		request<AISettings>("/ai-settings", { method: "PUT", body: JSON.stringify(settings) }),
	resetAISettings: () => request<AISettings>("/ai-settings", { method: "DELETE"}),
	stories: async () => (await request<{ stories: Story[] }>("/stories")).stories,
	createStory: (title: string) => request<Story>("/stories", {
		method: "POST",
		body: JSON.stringify({ title }),
	}),
	deleteStory: (storyId: string) => request<void>(`/stories/${storyId}`, { method: "DELETE" }),
	story: (storyId: string) => request<StoryDetails>(`/stories/${storyId}`),
	storyIndexStatus: (storyId: string) => request<{ chapters: Array<Pick<Chapter, "id" | "revision" | "word_count" | "index_status" | "index_error" | "bible_scan_revision" | "bible_scan_error">> }>(`/stories/${storyId}/index-status`),
	updateStory: (storyId: string, changes: Partial<Pick<Story, "title" | "collection_name" | "scan_interval_words" | "external_analysis_enabled">>) =>
		request<Story>(`/stories/${storyId}`, { method: "PATCH", body: JSON.stringify(changes) }),
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
	chapterRevisions: async (chapterId: string) => (await request<{ revisions: ChapterRevisionSummary[] }>(`/stories/chapters/${chapterId}/revisions`)).revisions,
	restoreChapterRevision: (chapterId: string, revisionNumber: number) => request<Chapter>(`/stories/chapters/${chapterId}/revisions/${revisionNumber}/restore`, { method: "POST" }),
	chapterStatus: (chapterId: string) => request<Pick<Chapter, "id" | "revision" | "word_count" | "index_status" | "index_error" | "bible_scan_revision" | "bible_scan_error">>(`/stories/chapters/${chapterId}/status`),
	retryChapterIndex: (chapterId: string) => request<{ id: string; index_status: string }>(`/stories/chapters/${chapterId}/reindex`, { method: "POST" }),
	importManuscript: (storyId: string, filename: string, content: string) =>
		request<{ chapters: Chapter[] }>(`/stories/${storyId}/import`, {
			method: "POST",
			body: JSON.stringify({ filename, content }),
		}),
	bible: async (storyId: string) => (await request<{ entries: BibleEntry[] }>(`/stories/${storyId}/bible`)).entries,
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
	latestScan: (chapterId: string) => request<ChapterScan>(`/stories/chapters/${chapterId}/scan`),
	scanChapter: (chapterId: string, force = false) => request<{ scan_id: string; finding_count: number; chapter_revision: number; reused: boolean }>(
		`/stories/chapters/${chapterId}/scan${force ? "?force=true" : ""}`, { method: "POST" },
	),
	markIntentional: (findingId: string, intentional = true) =>
		request<{ id: string; intentional: boolean }>(`/stories/findings/${findingId}/intentional`, {
			method: "PATCH",
			body: JSON.stringify({ intentional }),
		}),
	reviewFinding: (findingId: string, reviewStatus: "open" | "resolved" | "dismissed") => request<{ id: string; review_status: ContinuityFinding["review_status"]; intentional: boolean }>(`/stories/findings/${findingId}/review`, { method: "PATCH", body: JSON.stringify({ review_status: reviewStatus }) }),
	editingFolders: async () => (await request<{ folders: DraftFolder[] }>("/editing/folders")).folders,
	createEditingFolder: (name: string) => request<DraftFolder>("/editing/folders", {
		method: "POST",
		body: JSON.stringify({ name }),
	}),
	renameEditingFolder: (folderId: string, name: string) => request<DraftFolder>(`/editing/folders/${folderId}`, {
		method: "PATCH",
		body: JSON.stringify({ name }),
	}),
	deleteEditingFolder: (folderId: string) => request<void>(`/editing/folders/${folderId}`, { method: "DELETE" }),
	draftFiles: async (folderId?: string) => {
		const query = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : "";
		return (await request<{ files: DraftFile[] }>(`/editing/files${query}`)).files;
	},
	uploadDraftFile: (file: File, folderId: string) => {
		const form = new FormData();
		form.set("file", file);
		form.set("folder_id", folderId);
		return request<DraftFile>("/editing/files", { method: "POST", body: form });
	},
	updateDraftFile: (fileId: string, changes: { title?: string; folder_id?: string }) =>
		request<DraftFile>(`/editing/files/${fileId}`, { method: "PATCH", body: JSON.stringify(changes) }),
	deleteDraftFile: (fileId: string) => request<void>(`/editing/files/${fileId}`, { method: "DELETE" }),
	draftFileContentUrl: (fileId: string, inline = false) =>
		`${API_BASE_URL}/editing/files/${fileId}/content${inline ? "?inline=true" : ""}`,
};
