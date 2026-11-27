import { ConfirmProvider } from "@/components/confirm-dialog";
import { WikiShell } from "@/components/wiki/wiki-shell";

export default async function WikiLayout({
	children,
	params,
}: {
	children: React.ReactNode;
	params: Promise<{ storyId: string }>;
}) {
	const { storyId } = await params;
	return (
		<ConfirmProvider>
			<WikiShell storyId={storyId}>{children}</WikiShell>
		</ConfirmProvider>
	);
}
