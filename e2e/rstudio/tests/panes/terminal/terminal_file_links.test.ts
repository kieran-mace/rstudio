// Opening files from paths printed in the Terminal pane with Ctrl/Cmd+Click.
//
// The terminal's file-link provider sends every token on the hovered line to the
// session, which resolves them against the terminal's working directory; only
// tokens naming an existing file become links, and a link is only marked --
// and only activates -- while the platform's open-link modifier is held (Cmd
// on macOS, Ctrl elsewhere).

import type { Page } from 'playwright';
import { test, expect } from '@fixtures/rstudio.fixture';
import { TIMEOUTS } from '@utils/constants';
import { AceEditor } from '@pages/ace_editor.page';
import { documentCloseAllNoSave, executeCommand, waitForActiveDocument } from '@utils/commands';
import { seedSandboxFile } from '@utils/files';
import { rPathLiteral } from '@utils/r';
import { useSuiteSandbox } from '@utils/sandbox';
import {
  type Point,
  captureResult,
  focusTerminal,
  killAllTerminals,
  locateTerminalText,
  openTerminal,
  terminalLinkUnderPointer,
} from '@utils/terminal';

const FILE_CONTENT = 'first <- 1\nsecond <- 2\nthird <- 3\n';

/** The modifier that turns a printed path into a link on this platform. */
const MODIFIER = process.platform === 'darwin' ? 'Meta' : 'Control';

async function runInTerminal(page: Page, command: string): Promise<void> {
  await page.keyboard.type(command);
  await page.keyboard.press('Enter');
}

/**
 * Hover the terminal text `text` until the terminal reports a link under the
 * pointer,
 * and return the point to click. `text` should be the tail of the printed
 * path (the file name), which belongs to a link naming the file wherever the
 * path wraps. The modifier is pressed first, since nothing is marked as a link
 * without it, and is left held for the caller to release.
 *
 * The raw mouse is used throughout, at the cells the text is drawn in (the
 * terminal is a canvas). Link resolution is asynchronous and the terminal's
 * working directory reaches the session a little after a `cd`, so an early
 * hover can come back empty; the terminal keeps a row's links until it is
 * next written to or the modifier changes, hence releasing and pressing the
 * modifier again before each retry, with a hop to the row above.
 */
async function hoverFileLink(page: Page, text: string): Promise<Point> {
  let point: Point = { x: 0, y: 0 };
  await expect(async () => {
    await page.keyboard.up(MODIFIER);
    point = await locateTerminalText(page, text);
    // off the row first, so arriving on it is a fresh hover
    await page.mouse.move(point.x, point.y - 20);
    await page.keyboard.down(MODIFIER);
    await page.mouse.move(point.x, point.y);
    await expect
      .poll(() => terminalLinkUnderPointer(page), { timeout: TIMEOUTS.settleDelay })
      .toBe(true);
  }).toPass({ timeout: TIMEOUTS.fileOpen });

  return point;
}

/** Click a hovered link, releasing the modifier hoverFileLink left held. */
async function clickFileLink(page: Page, point: Point): Promise<void> {
  try {
    await page.mouse.click(point.x, point.y);
  } finally {
    await page.keyboard.up(MODIFIER);
  }
}

const sandbox = useSuiteSandbox();

test.describe.serial('Terminal: file paths open with Ctrl/Cmd+Click', () => {
  let isWindows = false;

  test.beforeAll(async ({ rstudioPage: page }) => {
    isWindows = (await captureResult(page, '.Platform$OS.type')) === 'windows';
  });

  test.beforeEach(async ({ rstudioPage: page }) => {
    await documentCloseAllNoSave(page);
    await killAllTerminals(page);
    await openTerminal(page);
  });

  test.afterEach(async ({ rstudioPage: page }) => {
    // a test that failed mid-hover can leave the modifier held
    await page.keyboard.up(MODIFIER).catch(() => {});
    await killAllTerminals(page).catch(() => {});
    await documentCloseAllNoSave(page).catch(() => {});
    await executeCommand(page, 'activateConsole').catch(() => {});
  });

  test('an absolute path with a :line suffix opens the file at that line', async ({ rstudioPage: page }) => {
    // Against a remote server the seed is written through the R console,
    // which takes focus away from the terminal.
    const fullPath = await seedSandboxFile(page, sandbox.dir, 'link_absolute.R', FILE_CONTENT);
    await focusTerminal(page);

    // On Windows the sandbox path comes back with backslashes, which an
    // unquoted bash `echo` strips (Git Bash is the default shell there); print
    // the forward-slash form, which every shell echoes verbatim and the
    // session resolves just the same.
    await runInTerminal(page, `echo ${fullPath.replace(/\\/g, '/')}:2`);
    const link = await hoverFileLink(page, 'link_absolute.R:2');
    await clickFileLink(page, link);

    await waitForActiveDocument(page, fullPath, TIMEOUTS.fileOpen);
    const editor = new AceEditor(page, '');
    await expect.poll(() => editor.getValue()).toBe(FILE_CONTENT);
    await expect.poll(async () => (await editor.getCursorPosition()).row).toBe(1);
  });

  test('a relative path resolves against the terminal working directory', async ({ rstudioPage: page }) => {
    test.skip(isWindows, 'the test drives a POSIX shell (cd + ls)');

    const fileName = 'link_relative.R';
    const terminalDir = `${sandbox.dir}/terminal`;
    const fullPath = await seedSandboxFile(page, sandbox.dir, `terminal/${fileName}`, FILE_CONTENT);

    // R stays in the sandbox root, with a same-named decoy. Resolving against
    // R's working directory must not open that file instead of the terminal's.
    await seedSandboxFile(page, sandbox.dir, fileName, 'stop("wrong working directory")\n');
    expect(await captureResult(page, 'getwd()')).toBe(sandbox.dir);
    await focusTerminal(page);

    await runInTerminal(page, `cd "${terminalDir}"`);
    // Wait for the session's cwd poller before hovering: the decoy is also a
    // valid link while the terminal still reports its previous directory.
    await expect.poll(() => captureResult(page,
      `normalizePath(rstudioapi::terminalContext(rstudioapi::terminalList()[[1]])$working_dir) == normalizePath(${rPathLiteral(terminalDir)})`,
    ), { timeout: TIMEOUTS.fileOpen }).toBe('TRUE');
    await focusTerminal(page);
    await runInTerminal(page, 'ls');
    const link = await hoverFileLink(page, fileName);
    await clickFileLink(page, link);

    await waitForActiveDocument(page, fullPath, TIMEOUTS.fileOpen);
    const editor = new AceEditor(page, '');
    await expect.poll(() => editor.getValue()).toBe(FILE_CONTENT);
  });

  test('a path is only marked as a link while the modifier is held', async ({ rstudioPage: page }) => {
    const fullPath = await seedSandboxFile(page, sandbox.dir, 'link_modifier.R', FILE_CONTENT);
    await focusTerminal(page);

    await runInTerminal(page, `echo ${fullPath.replace(/\\/g, '/')}`);
    await hoverFileLink(page, 'link_modifier.R');

    // releasing the modifier unmarks the link without the pointer moving
    await page.keyboard.up(MODIFIER);
    await expect.poll(() => terminalLinkUnderPointer(page)).toBe(false);

    // and pressing it again marks it once more
    await page.keyboard.down(MODIFIER);
    await expect.poll(() => terminalLinkUnderPointer(page)).toBe(true);
    await page.keyboard.up(MODIFIER);
  });
});
