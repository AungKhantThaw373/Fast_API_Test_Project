import { EntityListPage } from "@/components/wiki/entity-list-page";

export default async function WikiPage({
	params,
	searchParams,
}: {
	params: Promise<{ storyId: string }>;
	searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
	const { storyId } = await params;
	const filters = await searchParams;
	return <EntityListPage storyId={storyId} searchParams={filters} />;
}
