import { ArcPage } from "@/components/wiki/arc-page";

export default async function ArcRoute({
	params,
}: {
	params: Promise<{ storyId: string; arcId: string }>;
}) {
	const { storyId, arcId } = await params;
	return <ArcPage storyId={storyId} arcId={arcId} />;
}
