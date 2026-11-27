'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export function StoryMobileNav({ storyId }: { storyId: string }) {
	const pathname = usePathname();
	const items = [
		{ href: `/stories/${storyId}`, label: 'Write' },
		{ href: `/stories/${storyId}/wiki`, label: 'Wiki' },
		{ href: `/stories/${storyId}/wiki/review`, label: 'Review' },
		{ href: `/stories/${storyId}/wiki/threads`, label: 'Threads' },
	];
	function isActive(href: string, label: string) {
		if (href === `/stories/${storyId}`) return pathname === href;
		if (label === 'Wiki') {
			return pathname === href || (pathname.startsWith(href + '/') && !pathname.startsWith(href + '/review') && !pathname.startsWith(href + '/threads'));
		}
		return pathname === href || pathname.startsWith(href + '/');
	}
	return (
		<nav className="story-mobile-nav" aria-label="Story sections">
			{items.map((item) => <Link key={item.href} href={item.href} aria-current={isActive(item.href, item.label) ? 'page' : undefined}>{item.label}</Link>)}
		</nav>
	);
}