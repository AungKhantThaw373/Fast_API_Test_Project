import { InboxPage } from "@/components/wiki/inbox-page";

export default async function ReviewPage({ params }: { params: Promise<{ storyId: string }> }) {
	const { storyId } = await params;
	return <InboxPage storyId={storyId} />;
}
