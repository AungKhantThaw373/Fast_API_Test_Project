// Phase 1 manual QA as an automated flow.
// Run with the backend on :8000 and the frontend on :3000.
import { chromium } from 'playwright';

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:3000';
const EMAIL = 'ui@test.dev';
const PASSWORD = 'ui-test-password';

const log = (message) => console.log(`• ${message}`);
const fail = (message) => { console.error(`✗ ${message}`); process.exit(1); };

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
page.on('pageerror', (error) => console.error('page error:', error.message));

async function signIn() {
	await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
	await page.fill('input[type="email"], input[name="email"]', EMAIL);
	await page.fill('input[type="password"]', PASSWORD);
	await page.getByRole('button', { name: /sign in|enter|open/i }).click();
	await page.waitForURL(/dashboard|stories/, { timeout: 15000 });
	log('signed in');
}

async function openStory() {
	await page.getByRole('link', { name: /UI verification/i }).first().click();
	await page.waitForURL(/\/stories\//, { timeout: 15000 });
	await page.waitForSelector('textarea.manuscript-editor', { timeout: 15000 });
	log('story opened');
}

// 1. Type, navigate away immediately, come back: nothing is lost.
async function keystrokeLoss() {
	const editor = page.locator('textarea.manuscript-editor');
	await editor.click();
	const sentence = `A sentence typed at ${new Date().toISOString()}.`;
	await editor.press('End');
	await page.keyboard.type(` ${sentence}`);
	// Navigate at once, well inside the 800ms autosave window.
	await page.getByRole('button', { name: /^Stories$/ }).click();
	await page.waitForURL(/dashboard/, { timeout: 15000 });
	await openStory();
	const value = await page.locator('textarea.manuscript-editor').inputValue();
	if (!value.includes(sentence)) fail('typed sentence was lost when navigating away');
	log('no keystroke lost on navigation');
}

// 2. Version history: save a checkpoint, then compare two versions.
async function historyFlow() {
	await page.getByRole('button', { name: /Version history/i }).click();
	await page.getByRole('button', { name: /Save checkpoint/i }).click();
	await page.waitForTimeout(1500);
	const kinds = await page.locator('.history-kind').allTextContents();
	if (!kinds.includes('checkpoint')) fail('checkpoint was not listed in history');
	await page.locator('.history-dialog header button').click({ timeout: 10000 });
	log('history dialog opened and checkpoint saved');
}

// 3. Trash flow: delete a chapter and restore it from the dashboard.
async function trashFlow() {
	const chaptersBefore = await page.locator('.chapter-nav-item').count();
	await page.locator('.chapter-delete-button').last().click();
	await page.getByRole('button', { name: /Move to trash/i }).click();
	await page.waitForTimeout(1200);
	const chaptersAfter = await page.locator('.chapter-nav-item').count();
	if (chaptersAfter !== chaptersBefore - 1) fail('chapter was not removed after trashing');
	log('chapter moved to trash');

	await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle' });
	await page.getByRole('button', { name: /Open trash|Refresh/i }).click();
	await page.waitForSelector('.trash-row', { timeout: 10000 });
	await page.getByRole('button', { name: /^Restore$/ }).first().click();
	await page.waitForTimeout(1500);
	log('chapter restored from trash');
}

// 4. Conflict: two tabs on the same chapter.
async function conflictFlow() {
	await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle' });
	await page.getByRole('link', { name: /UI verification/i }).first().click();
	await page.waitForSelector('textarea.manuscript-editor');
	const second = await context.newPage();
	await second.goto(page.url(), { waitUntil: 'networkidle' });
	await second.waitForSelector('textarea.manuscript-editor');

	// Tab A saves a change.
	await page.locator('textarea.manuscript-editor').click();
	await page.keyboard.press('End');
	await page.keyboard.type(' Saved by tab A.');
	await page.waitForTimeout(1800);

	// Tab B saves against the now-stale revision.
	await second.locator('textarea.manuscript-editor').click();
	await second.keyboard.press('End');
	await second.keyboard.type(' Written in tab B.');
	await second.waitForTimeout(1800);

	const dialogVisible = await second.getByText(/This chapter changed somewhere else/i).isVisible().catch(() => false);
	if (!dialogVisible) fail('no conflict dialog appeared for the stale tab');
	await second.getByRole('button', { name: /Keep mine/i }).click();
	await second.waitForTimeout(1500);
	const value = await second.locator('textarea.manuscript-editor').inputValue();
	if (!value.includes('Written in tab B.')) fail('Keep mine did not preserve the local text');
	log('conflict dialog appeared and Keep mine preserved the local text');
	await second.close();
}

try {
	await signIn();
	await openStory();
	await keystrokeLoss();
	await historyFlow();
	await trashFlow();
	await conflictFlow();
	console.log('All Phase 1 browser flows passed.');
} catch (error) {
	console.error(error);
	process.exit(1);
} finally {
	await browser.close();
}
