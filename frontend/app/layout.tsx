import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
	title: "Stillroom — Writing and Editing",
	description: "A quiet chapter writing studio and a structured library for story draft files.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
	return <html lang="en"><body>{children}</body></html>;
}
