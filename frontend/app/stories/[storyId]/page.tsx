import StoryStudio from './studio';

export default async function StoryPage({ params }: { params: Promise<{ storyId: string }> }) {
	const { storyId } = await params;
	return <StoryStudio storyId={storyId} />;
}
