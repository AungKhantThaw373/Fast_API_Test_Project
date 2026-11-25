"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { qk, type EntityFilters } from "@/lib/query-keys";

export function useStory(storyId: string) {
	return useQuery({
		queryKey: qk.story(storyId),
		queryFn: () => api.story(storyId),
		enabled: Boolean(storyId),
	});
}

export function useChapters(storyId: string) {
	return useQuery({
		queryKey: qk.chapters(storyId),
		queryFn: () => api.chapters(storyId),
		enabled: Boolean(storyId),
	});
}

export function useEntities(storyId: string, filters: EntityFilters) {
	return useQuery({
		queryKey: qk.entities(storyId, filters),
		queryFn: () => api.entities(storyId, filters),
		enabled: Boolean(storyId),
	});
}

export function useEntity(entityId: string) {
	return useQuery({
		queryKey: qk.entity(entityId),
		queryFn: () => api.entity(entityId),
		enabled: Boolean(entityId),
	});
}

export function useEntityFacts(entityId: string) {
	return useQuery({
		queryKey: qk.entityFacts(entityId),
		queryFn: () => api.entityFacts(entityId),
		enabled: Boolean(entityId),
	});
}

export function useEntityAppearances(entityId: string) {
	return useQuery({
		queryKey: qk.entityAppearances(entityId),
		queryFn: () => api.entityAppearances(entityId),
		enabled: Boolean(entityId),
	});
}

export function useEntityRelationships(entityId: string) {
	return useQuery({
		queryKey: qk.entityRelationships(entityId),
		queryFn: () => api.entityRelationships(entityId),
		enabled: Boolean(entityId),
	});
}

export function useThreads(storyId: string) {
	return useQuery({
		queryKey: qk.threads(storyId),
		queryFn: () => api.threads(storyId),
		enabled: Boolean(storyId),
	});
}

export function useInbox(storyId: string, kind?: string) {
	return useQuery({
		queryKey: [...qk.inbox(storyId), kind ?? "all"],
		queryFn: () => api.inbox(storyId, { kind, limit: 200 }),
		enabled: Boolean(storyId),
	});
}

export function useExceptions(storyId: string) {
	return useQuery({
		queryKey: qk.exceptions(storyId),
		queryFn: () => api.exceptions(storyId),
		enabled: Boolean(storyId),
	});
}

export function useEntitySearch(storyId: string, term: string) {
	return useQuery({
		queryKey: qk.entitySearch(storyId, term),
		queryFn: () => api.searchEntities(storyId, term),
		enabled: Boolean(storyId && term.trim()),
		staleTime: 10_000,
	});
}

export function useArcs(storyId: string) {
	return useQuery({
		queryKey: qk.arcs(storyId),
		queryFn: () => api.arcs(storyId),
		enabled: Boolean(storyId),
	});
}

export function useCanonCoverage(storyId: string) {
	return useQuery({
		queryKey: qk.canon(storyId),
		queryFn: () => api.canonCoverage(storyId),
		enabled: Boolean(storyId),
	});
}
