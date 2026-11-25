import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
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
		const child = spawn(process.execPath, [join(here, script)], { cwd: join(here, '..'), stdio: 'inherit' });
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