export default async function ReviewPage({ params }: { params: Promise<{ storyId: string }> }) {
	const { storyId } = await params;
	return (
		<div className="wiki-page">
			<header className="wiki-page-head">
				<div>
					<div className="eyebrow">DECISIONS WAITING</div>
					<h1>Review inbox</h1>
				</div>
			</header>
			<p className="wiki-empty-note">Proposals and continuation findings for {storyId} arrive here.</p>
		</div>
	);
}
