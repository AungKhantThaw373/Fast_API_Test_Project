// The API issues a readable csrf cookie on safe requests. Browser tests talk to
// the API directly, so they have to echo it on every write just like lib/api.ts.
export async function csrfToken(api) {
	const response = await fetch(api + '/health');
	const cookies = response.headers.getSetCookie?.() ?? [response.headers.get('set-cookie') ?? ''];
	const cookie = cookies.find((value) => value.startsWith('csrf='));
	if (!response.ok || !cookie) throw new Error('no csrf cookie from ' + api);
	return cookie.split(';')[0].slice('csrf='.length);
}

export function apiHeaders(csrf, cookie) {
	return {
		'Content-Type': 'application/json',
		'X-CSRF-Token': csrf,
		Cookie: ['csrf=' + csrf, cookie].filter(Boolean).join('; '),
	};
}