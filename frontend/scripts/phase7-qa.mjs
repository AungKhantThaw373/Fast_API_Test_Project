import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { apiHeaders, csrfToken } from './qa-csrf.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const API = 'http://127.0.0.1:8000';
const PASSWORD = 'correct horse battery';
const stamp = Date.now();
const csrf = await csrfToken(API);
const email = 'p7suite' + stamp + '@example.com';

async function post(path, headers, body) {
	return fetch(API + path, { method: 'POST', headers, body });
}

// One account and one login for all eight suites: the product intentionally
// limits registration to 3/hour and logins to 5/15 minutes per address.
const registration = await post('/register', apiHeaders(csrf), JSON.stringify({ username: 'p7suite' + stamp, email, password: PASSWORD }));
if (!registration.ok) throw new Error('QA register failed: ' + registration.status + ' ' + await registration.text());
const login = await post('/token', { ...apiHeaders(csrf), 'Content-Type': 'application/x-www-form-urlencoded' }, new URLSearchParams({ username: email, password: PASSWORD }));
const rawCookie = (login.headers.get('set-cookie') || '').split(';')[0];
if (!login.ok || !rawCookie) throw new Error('QA login failed: ' + login.status + ' ' + await login.text());

const suites = [
	['editor and inline canon', 'p7-editor-smoke.mjs'],
	['editor marks and keyboard exits', 'p7-marks-smoke.mjs'],
	['command palette actions and recents', 'p7-palette-smoke.mjs'],
	['style and line-edit panel', 'p7-style-smoke.mjs'],
	['cited recaps', 'p7-recap-smoke.mjs'],
	['thread board and keyboard drag', 'p7-thread-smoke.mjs'],
	['exports and backup restore', 'p7-export-smoke.mjs'],
	['responsive layout and focus', 'p7-responsive-smoke.mjs'],
];

const outcomes = [];
for (const [name, script] of suites) {
	console.log('\n=== ' + name + ' ===');
	const code = await new Promise((resolve) => {
		const child = spawn(process.execPath, [join(here, script)], {
			cwd: join(here, '..'),
			stdio: 'inherit',
			env: { ...process.env, QA_COOKIE: rawCookie },
		});
		child.on('exit', (value) => resolve(value ?? 1));
		child.on('error', () => resolve(1));
	});
	outcomes.push({ name, code });
}

const failed = outcomes.filter((outcome) => outcome.code !== 0);
console.log('\nPhase 7 QA: ' + (outcomes.length - failed.length) + '/' + outcomes.length + ' suites passed.');
if (failed.length) {
	for (const outcome of failed) console.log('FAILED ' + outcome.name + ' (exit ' + outcome.code + ')');
	process.exit(1);
}