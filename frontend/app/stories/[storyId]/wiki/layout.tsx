import { WikiShell } from "@/components/wiki/wiki-shell";

export default async function WikiLayout({
	children,
	params,
}: {
	children: React.ReactNode;
	params: Promise<{ storyId: string }>;
}) {
	const { storyId } = await params;
	return <WikiShell storyId={storyId}>{children}</WikiShell>;
}
