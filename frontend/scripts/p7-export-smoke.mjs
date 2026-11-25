import { chromium } from 'playwright';
import { copyFile, readFile, stat } from 'node:fs/promises';

const WEB = 'http://127.0.0.1:3000';
const API = 'http://127.0.0.1:8000';
const stamp = Date.now();
const PASSWORD = 'correct horse battery';
const results = [];
function check(name, condition, detail = '') {
	results.push({ name, ok: Boolean(condition) });
	console.log((condition ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : ''));
}
async function request(path, options = {}, cookie) {
	const response = await fetch(API + path, { ...options, headers: { 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}), ...options.headers } });
	const text = await response.text();
	if (!response.ok) throw new Error(path + ' -> ' + response.status + ' ' + text);
	return text ? JSON.parse(text) : null;
}

const email = 'p7export' + stamp + '@example.com';
await request('/register', { method: 'POST', body: JSON.stringify({ username: 'p7export' + stamp, email, password: PASSWORD }) });
const token = await fetch(API + '/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ username: email, password: PASSWORD }) });
const rawCookie = (token.headers.get('set-cookie') || '').split(';')[0];
const story = await request('/stories', { method: 'POST', body: JSON.stringify({ title: 'Export ' + stamp }) }, rawCookie);
const chapter = await request('/stories/' + story.id + '/chapters', { method: 'POST', body: JSON.stringify({ title: 'The gate', content: 'Mira opens the gate.\n\n* * *\n\nThe lantern is already lit.\n' }) }, rawCookie);
const entity = await request('/stories/' + story.id + '/entities', { method: 'POST', body: JSON.stringify({ name: 'Mira Voss', entity_type: 'character' }) }, rawCookie);
await request('/entities/' + entity.id + '/facts', { method: 'POST', body: JSON.stringify({ predicate: 'carries', value_text: 'a lantern', chapter_id: chapter.id, quote: 'The lantern is already lit.', status: 'accepted' }) }, rawCookie);
await request('/stories/' + story.id + '/threads', { method: 'POST', body: JSON.stringify({ title: 'Who lit the lantern?', setup_chapter_id: chapter.id, linked_entity_ids: [entity.id] }) }, rawCookie);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(String(error)));
const [name, value] = rawCookie.split('=');
await context.addCookies([{ name, value, domain: '127.0.0.1', path: '/' }]);
await page.goto(WEB + '/stories/' + story.id);
await page.getByRole('button', { name: /Export manuscript/ }).click();
await page.getByRole('dialog', { name: 'Export' }).waitFor();
check('export panel opens', await page.getByText('Whole-story backup').isVisible());

async function download(label) {
	const [event] = await Promise.all([
		page.waitForEvent('download', { timeout: 120000 }),
		page.getByRole('button', { name: label }).click(),
	]);
	const path = await event.path();
	return { path, filename: event.suggestedFilename(), size: path ? (await stat(path)).size : 0, head: path ? (await readFile(path)).subarray(0, 4).toString('latin1') : '' };
}

const docx = await download('Download Word');
check('DOCX download is a real archive', docx.size > 5000 && docx.head.startsWith('PK') && docx.filename.endsWith('.docx'), `${docx.filename} ${docx.size} bytes`);
if (docx.path) await copyFile(docx.path, '../tmp-export.docx');
await page.getByLabel('EPUB').check();
const epub = await download('Download EPUB');
check('EPUB download is a real archive', epub.size > 3000 && epub.head.startsWith('PK') && epub.filename.endsWith('.epub'), `${epub.filename} ${epub.size} bytes`);
await page.getByLabel('PDF').check();
const pdf = await download('Download PDF');
check('PDF download is a real PDF', pdf.size > 5000 && pdf.head.startsWith('%PDF') && pdf.filename.endsWith('.pdf'), `${pdf.filename} ${pdf.size} bytes`);
if (pdf.path) await copyFile(pdf.path, '../tmp-export.pdf');

await page.getByLabel('Markdown').check();
const markdown = await download('Download Markdown');
const markdownText = markdown.path ? await readFile(markdown.path, 'utf8') : '';
check('Markdown includes manuscript and wiki appendix', markdownText.includes('## Chapter 1: The gate') && markdownText.includes('Mira Voss') && markdownText.includes('⁂'), `${markdown.size} bytes`);

const [backupEvent] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download JSON backup' }).click()]);
const backupPath = await backupEvent.path();
const backup = JSON.parse(backupPath ? await readFile(backupPath, 'utf8') : '{}');
check('backup carries chapters and graph', backup.format_version === 1 && backup.chapters.length === 1 && backup.entities.length === 1 && backup.threads.length === 1, `${backupPath}`);

await page.locator('input[type=file][accept*="json"]').setInputFiles(backupPath);
await page.waitForURL(new RegExp('/stories/(?!' + story.id + ')[0-9a-f-]+'), { timeout: 30000 });
check('restoring creates a new story route', !page.url().endsWith(story.id), page.url());
await page.getByText('The gate', { exact: true }).first().waitFor({ timeout: 20000 });
check('restored chapter is present in the new story', true);

check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
await browser.close();
const failed = results.filter((item) => !item.ok);
console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, backup: backupPath }));
if (failed.length) process.exit(1);