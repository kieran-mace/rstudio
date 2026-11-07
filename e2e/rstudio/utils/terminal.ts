// Helpers for driving the Terminal pane through a real shell.
//
// The terminal emulator (ghostty-web) draws on a canvas, so its text is not in
// the DOM. Terminal state is observed via rstudioapi::terminalBuffer() in the
// R console (the server's copy), or read from the emulator in the page
// (terminalRows() and friends: what the client actually shows). Every console
// round trip moves focus away from the terminal; use focusTerminal() before
// typing.

import type { Page } from 'playwright';
import { test, expect } from '@fixtures/rstudio.fixture';
import { TIMEOUTS } from '@utils/constants';
import { executeInConsole, CONSOLE_OUTPUT } from '@pages/console_pane.page';
import { rStringLiteral } from '@utils/r';

export const TERMINAL_TAB = '#rstudio_workbench_tab_terminal';
/** The terminal widget, one per terminal (hidden ones stay mounted). */
export const XTERM_SELECTOR = '.xterm-rstudio';

/** Evaluate an R expression in the console and return its printed value. */
export async function captureResult(page: Page, rExpression: string): Promise<string> {
  const marker = `__TERM_${Date.now()}__`;
  // Gate on R reporting idle so the marker pair has fully written by the time
  // we read the console.
  await executeInConsole(
    page,
    `cat(${rStringLiteral(marker)}, ${rExpression}, ${rStringLiteral(marker)})`,
    { wait: true },
  );

  const pattern = new RegExp(`${marker}\\s+(.*?)\\s+${marker}`, 's');
  const output = await page.locator(CONSOLE_OUTPUT).innerText();
  const match = output.match(pattern);
  if (!match) throw new Error(`captureResult: markers not found for "${rExpression}"`);
  return match[1].trim();
}

export async function killAllTerminals(page: Page): Promise<void> {
  await executeInConsole(page, 'rstudioapi::terminalKill(rstudioapi::terminalList())', {
    wait: true,
  });
}

/**
 * Select the Terminal tab and give the xterm widget keyboard focus. Needed
 * after anything that drives the R console (captureResult, seedSandboxFile on
 * a remote server, ...), since the console path clicks the Console tab and
 * focuses the console input.
 */
export async function focusTerminal(page: Page): Promise<void> {
  await page.locator(TERMINAL_TAB).click();
  // Other terminal sessions remain mounted in the hidden deck panels.
  const terminal = page.locator(`${XTERM_SELECTOR}:visible`);
  await expect(terminal).toBeVisible({ timeout: TIMEOUTS.consoleReady });
  await terminal.click();
}

/** Create a terminal and return once its shell is echoing a prompt and focused for typing. */
export async function openTerminal(page: Page): Promise<void> {
  await executeInConsole(page, 'rstudioapi::terminalCreate(show = TRUE)');
  await expect(page.locator(XTERM_SELECTOR)).toBeVisible({ timeout: TIMEOUTS.consoleReady });
  await expect(page.locator(TERMINAL_TAB)).toHaveAttribute('aria-selected', 'true', {
    timeout: TIMEOUTS.consoleReady,
  });

  // The xterm widget becomes visible before the shell has attached to the pty
  // and echoed its prompt; keystrokes sent before then are dropped (observed
  // on macOS CI: the buffer held only the prompt, every typed line lost).
  // Wait until the buffer has a non-empty line -- proof the shell is echoing.
  await expect
    .poll(
      () =>
        captureResult(
          page,
          '{ ids <- rstudioapi::terminalList(); ' +
            'length(ids) > 0 && any(nzchar(trimws(rstudioapi::terminalBuffer(ids[[1]])))) }',
        ),
      { timeout: TIMEOUTS.consoleReady },
    )
    .toBe('TRUE');

  await focusTerminal(page);
}

/**
 * Run `input` -- keystrokes that submit one or more shell commands at the
 * focused terminal -- then `landed`, which must throw until their effect is
 * observable. If it never is, interrupt the prompt and do both once more.
 *
 * A keystroke typed while the pty is being resized can be lost. Seen on
 * Windows CI (ConPTY + MSYS bash): "echo" arrived as "cho" and "expr 1 + 1"
 * as "expr 1+ 1", each within ~50ms of a process_set_size RPC. A resize tends
 * to land just as a test starts typing: a hidden terminal is not re-fit, so
 * a size change that comes up while openTerminal() has the Console tab
 * selected is sent when the Terminal tab is shown again. Nothing signals
 * that the shell is done
 * handling a resize, so detect the loss rather than trying to wait it out.
 * The size has settled by the second attempt.
 *
 * The commands must be safe to submit twice. A retry is recorded as a test
 * annotation so that lost input stays visible in the report.
 */
export async function retryTerminalInput(
  page: Page,
  input: () => Promise<void>,
  landed: () => Promise<void>,
): Promise<void> {
  await input();

  try {
    await landed();
    return;
  } catch (error) {
    test.info().annotations.push({
      type: 'terminal-input-retry',
      description: error instanceof Error ? error.message.split('\n')[0] : String(error),
    });
  }

  // `landed` may have driven the R console; Ctrl+C discards whatever is left
  // of the first attempt on the command line.
  await focusTerminal(page);
  await page.keyboard.press('Control+C');
  await input();
  await landed();
}

/** Where a terminal cell is drawn, in page coordinates. */
export interface Point {
  x: number;
  y: number;
}

/**
 * The rows of the visible terminal as its emulator holds them -- scrollback
 * first, then the screen -- one character per cell, blank cells as spaces.
 * XTermNative.createTerminal() exposes the emulator as the widget element's
 * `rstudioTerminal`.
 */
export async function terminalRows(page: Page): Promise<string[]> {
  return page.locator(`${XTERM_SELECTOR}:visible`).evaluate((element) => {
    const term = (element as any).rstudioTerminal;
    if (!term) return [];
    const buffer = term.buffer.active;
    const rows: string[] = [];
    for (let y = 0; y < buffer.length; y++) {
      const line = buffer.getLine(y);
      let text = '';
      for (let x = 0; line && x < line.length; x++) {
        const cell = line.getCell(x);
        if (cell && cell.getWidth() !== 0) text += cell.getChars() || ' ';
      }
      rows.push(text);
    }
    return rows;
  });
}

/**
 * Everything the visible terminal shows, with whitespace stripped (U+00B7
 * too, seen in terminal-derived text on some platforms) so that a match does
 * not depend on where a line wraps.
 */
export async function renderedTerminalText(page: Page): Promise<string> {
  return (await terminalRows(page)).join('').replace(/[\s\u00B7]+/g, '');
}

/**
 * The page point at the centre of cell (`column`, `row`) of the visible
 * terminal, `row` counted as terminalRows() counts them. The terminal must be
 * scrolled to the bottom, as it is after output, and the row on screen.
 */
export async function terminalCellPoint(page: Page, column: number, row: number): Promise<Point> {
  const point = await page.locator(`${XTERM_SELECTOR}:visible`).evaluate(
    (element, [column, row]) => {
      const term = (element as any).rstudioTerminal;
      const canvas = element.querySelector('canvas');
      if (!term || !canvas || !term.renderer) return null;
      const screenRow = row - (term.buffer.active.length - term.rows);
      if (screenRow < 0 || screenRow >= term.rows) return null;
      const box = canvas.getBoundingClientRect();
      return {
        x: box.left + (column + 0.5) * term.renderer.charWidth,
        y: box.top + (screenRow + 0.5) * term.renderer.charHeight,
      };
    },
    [column, row],
  );
  if (!point) throw new Error(`terminal cell (${column}, ${row}) is not on screen`);
  return point;
}

/**
 * Find the last occurrence of `text` in the visible terminal and return the
 * point at its middle. A long line wraps across rows, so each row is matched
 * joined with the one above it, and the point lands on the part of the match
 * in the lower row. Searching from the bottom finds a command's output rather
 * than its echo of the command line.
 */
export async function locateTerminalText(page: Page, text: string): Promise<Point> {
  const rows = await terminalRows(page);
  for (let i = rows.length - 1; i >= 0; i--) {
    const above = i > 0 ? rows[i - 1] : '';
    const index = (above + rows[i]).lastIndexOf(text);
    if (index === -1) continue;

    // a match lying wholly in the row above is found on that row's turn
    const end = index + text.length - above.length;
    if (end <= 0) continue;

    const start = Math.max(0, index - above.length);
    return terminalCellPoint(page, Math.floor((start + end - 1) / 2), i);
  }
  throw new Error(`terminal text not found: ${text}`);
}

/** Whether the visible terminal has text selected. */
export async function terminalHasSelection(page: Page): Promise<boolean> {
  return page.locator(`${XTERM_SELECTOR}:visible`).evaluate(
    (element) => !!(element as any).rstudioTerminal?.hasSelection(),
  );
}

/** Whether the pointer is over a link in the visible terminal. */
export async function terminalLinkUnderPointer(page: Page): Promise<boolean> {
  // the emulator shows a pointer cursor while a link is hovered
  return page
    .locator(`${XTERM_SELECTOR}:visible`)
    .evaluate((element) => (element as HTMLElement).style.cursor === 'pointer');
}
