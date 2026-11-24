import { EntityDetail } from "@/components/wiki/entity-detail";

export default async function WikiEntityPage({
	params,
}: {
	params: Promise<{ storyId: string; entityId: string }>;
}) {
	const { storyId, entityId } = await params;
	return <EntityDetail storyId={storyId} entityId={entityId} />;
}
