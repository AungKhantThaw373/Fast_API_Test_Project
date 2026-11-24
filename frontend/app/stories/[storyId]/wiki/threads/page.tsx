import { ThreadsPage } from "@/components/wiki/threads-page";

export default async function ThreadsRoute({ params }: { params: Promise<{ storyId: string }> }) {
	const { storyId } = await params;
	return <ThreadsPage storyId={storyId} />;
}
