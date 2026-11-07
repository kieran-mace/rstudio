// Ctrl+Shift+C / Ctrl+Shift+V copy and paste in the Terminal pane (#1687).
//
// The terminal handles both keys itself, on every platform: they send
// nothing to the shell, and they are the copy/paste keys of most
// terminal emulators. Cmd+C / Cmd+V on macOS keep working through the browser.
//
// Copies land on the system clipboard when the app runs headed (desktop), so a
// local run replaces whatever was on it.

import type { Page } from 'playwright';
import { test, expect } from '@fixtures/rstudio.fixture';
import { TIMEOUTS } from '@utils/constants';
import { executeCommand } from '@utils/commands';
import { ConsolePane, focusConsole } from '@pages/console_pane.page';
import {
  killAllTerminals,
  locateTerminalText,
  openTerminal,
  terminalHasSelection,
  terminalRows,
} from '@utils/terminal';

/**
 * Text of each terminal row with whitespace stripped (U+00B7 too, as in
 * terminal.test.ts), so a match doesn't depend on where a line wraps.
 */
async function rowTexts(page: Page): Promise<string[]> {
  const texts = await terminalRows(page);
  return texts.map((text) => text.replace(/[\s\u00B7]+/g, ''));
}

async function runInTerminal(page: Page, command: string): Promise<void> {
  await page.keyboard.type(command);
  await page.keyboard.press('Enter');
}

/**
 * Print a unique word on its own line and select it with a double-click.
 * Quotes split the word on the command line, so the only rendered row that
 * contains it whole is the output. Returns the word.
 */
async function printAndSelectWord(page: Page): Promise<string> {
  const stamp = Date.now();
  const word = `copy_me_${stamp}`;
  await runInTerminal(page, `echo copy_"me"_${stamp}`);

  await expect.poll(() => rowTexts(page), { timeout: TIMEOUTS.consoleReady }).toContain(word);
  await expect(async () => {
    // The terminal is a canvas: double-click the cells the word is drawn in.
    // Retry with fresh coordinates if more output moves it before the click.
    const point = await locateTerminalText(page, word);
    await page.mouse.dblclick(point.x, point.y);
    await expect.poll(() => terminalHasSelection(page), { timeout: 1000 }).toBe(true);
  }).toPass({ timeout: TIMEOUTS.consoleReady });
  return word;
}

test.describe.serial('Terminal: Ctrl+Shift+C / Ctrl+Shift+V', () => {
  test.beforeAll(async ({ rstudioPage: page }) => {
    // Where the browser has no plain-text paste key (macOS), the terminal
    // reads the clipboard through the async clipboard API, which Chromium
    // gates behind a permission. Electron contexts don't support this call
    // and don't need it: the desktop bridge reads the clipboard there.
    await page
      .context()
      .grantPermissions(['clipboard-read'])
      .catch(() => {});
  });

  test.beforeEach(async ({ rstudioPage: page }) => {
    await killAllTerminals(page);
    await openTerminal(page);
  });

  test.afterEach(async ({ rstudioPage: page }) => {
    await killAllTerminals(page).catch(() => {});
    await executeCommand(page, 'activateConsole').catch(() => {});
  });

  test('Ctrl+Shift+C copies the selection', async ({ rstudioPage: page }) => {
    const word = await printAndSelectWord(page);
    await page.keyboard.press('Control+Shift+C');

    // read the clipboard back through a plain paste into the Console input
    await focusConsole(page);
    await page.keyboard.press('ControlOrMeta+V');
    const consolePane = new ConsolePane(page);
    await expect.poll(() => consolePane.consoleInputValue()).toBe(word);
    await page.keyboard.press('Escape');
  });

  test('Ctrl+Shift+V pastes at the prompt', async ({ rstudioPage: page }) => {
    const word = await printAndSelectWord(page);
    await page.keyboard.press('Control+Shift+C');

    await page.keyboard.type('echo P=');
    await page.keyboard.press('Control+Shift+V');

    // where the paste is read asynchronously it lands a moment after the key;
    // join the rows so a command line that wraps still matches
    await expect.poll(async () => (await rowTexts(page)).join('')).toContain(`P=${word}`);
    await page.keyboard.press('Enter');

    // the echoed output starts its own row, so compare it whole: a doubled
    // paste (P=<word><word>) would still pass a substring match
    await expect.poll(() => rowTexts(page)).toContain(`P=${word}`);
  });
});
