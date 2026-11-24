export default async function ThreadsPage({ params }: { params: Promise<{ storyId: string }> }) {
	const { storyId } = await params;
	return (
		<div className="wiki-page">
			<header className="wiki-page-head">
				<div>
					<div className="eyebrow">OPEN QUESTIONS</div>
					<h1>Threads</h1>
				</div>
			</header>
			<p className="wiki-empty-note">Threads for {storyId} arrive here.</p>
		</div>
	);
}
