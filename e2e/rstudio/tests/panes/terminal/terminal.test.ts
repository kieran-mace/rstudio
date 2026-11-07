import { test, expect } from '@fixtures/rstudio.fixture';
import { TIMEOUTS } from '@utils/constants';
import { ConsolePaneActions } from '@actions/console_pane.actions';
import { AceEditor } from '@pages/ace_editor.page';
import { executeInConsole } from '@pages/console_pane.page';
import { executeCommand, getPref } from '@utils/commands';
import { useSuiteSandbox } from '@utils/sandbox';
import { rStringLiteral } from '@utils/r';
import {
  XTERM_SELECTOR,
  captureResult,
  killAllTerminals,
  focusTerminal,
  openTerminal,
  renderedTerminalText,
  retryTerminalInput,
} from '@utils/terminal';
import type { Page } from 'playwright';

/**
 * The color the visible terminal's canvas shows at the centre of its bottom
 * right cell -- below any output, so it is drawn in the terminal's background
 * -- along with the background the renderer was given, both as [r, g, b].
 */
async function terminalBackground(page: Page): Promise<{ drawn: number[]; theme: number[] }> {
  return page.locator(`${XTERM_SELECTOR}:visible`).evaluate((element) => {
    const term = (element as any).rstudioTerminal;
    const canvas = element.querySelector('canvas')!;
    const scale = canvas.width / canvas.getBoundingClientRect().width;
    const x = Math.floor((term.cols - 0.5) * term.renderer.charWidth * scale);
    const y = Math.floor((term.rows - 0.5) * term.renderer.charHeight * scale);
    const pixel = canvas.getContext('2d')!.getImageData(x, y, 1, 1).data;
    const probe = document.createElement('canvas').getContext('2d')!;
    probe.fillStyle = term.renderer.theme.background;
    probe.fillRect(0, 0, 1, 1);
    const theme = probe.getImageData(0, 0, 1, 1).data;
    return { drawn: [pixel[0], pixel[1], pixel[2]], theme: [theme[0], theme[1], theme[2]] };
  });
}

// Sandbox for file-creation test (terminal cwd is its own shell, so we
// pass the absolute sandbox path directly to the shell command).
const sandbox = useSuiteSandbox();

test.describe.serial('Terminal pane', () => {
  let consoleActions: ConsolePaneActions;

  test.beforeAll(async ({ rstudioPage: page }) => {
    consoleActions = new ConsolePaneActions(page);
  });

  test.afterEach(async ({ rstudioPage: page }) => {
    await killAllTerminals(page).catch(() => {});
    await executeCommand(page, 'activateConsole').catch(() => {});
  });

  test('a terminal can be created and is visible', async ({ rstudioPage: page }) => {
    await killAllTerminals(page);
    await openTerminal(page);

    const xterm = page.locator(XTERM_SELECTOR);
    const box = await xterm.boundingBox();
    expect(box, 'terminal widget should have a bounding box').not.toBeNull();
    expect(box!.width, 'terminal width').toBeGreaterThan(0);
    expect(box!.height, 'terminal height').toBeGreaterThan(0);
  });

  test('closing a terminal terminates its shell process', async ({ rstudioPage: page }) => {
    await killAllTerminals(page);
    await openTerminal(page);

    const pid = Number(
      await captureResult(page, 'rstudioapi::terminalContext(rstudioapi::terminalList()[[1]])$pid'),
    );
    expect(pid, 'shell pid').toBeGreaterThan(0);

    // "Close current terminal session", the pane's toolbar button
    await executeCommand(page, 'closeTerminal');
    await expect(page.locator(XTERM_SELECTOR)).toHaveCount(0, { timeout: TIMEOUTS.consoleReady });

    // Closing used to merely interrupt the shell, which an interactive shell
    // ignores: it lived on under the session, and the prompt it redrew was
    // logged as errors (#18976). Ask the OS whether the pid still exists:
    // signal 0 probes without killing on POSIX; tasklist filters by pid on
    // Windows.
    const isRunning =
      `{ pid <- ${pid}; if (.Platform$OS.type == "windows") ` +
      `any(grepl(sprintf('"%d"', pid), system2("tasklist", c("/FI", shQuote(sprintf("PID eq %d", pid)), "/NH", "/FO", "CSV"), stdout = TRUE), fixed = TRUE)) ` +
      `else tools::pskill(pid, 0) }`;
    await expect
      .poll(() => captureResult(page, isRunning), { timeout: TIMEOUTS.consoleReady })
      .toBe('FALSE');
  });

  test('we can run commands in the terminal', async ({ rstudioPage: page }) => {
    await killAllTerminals(page);
    await openTerminal(page);

    // After openTerminal returns, the terminal tab is selected and the
    // terminal is focused. Type the command via the page keyboard, then wait for the
    // terminal buffer to include the result line. Poll via
    // rstudioapi::terminalBuffer, the server's copy of the output.
    await retryTerminalInput(
      page,
      async () => {
        await page.keyboard.type('expr 1 + 1');
        await page.keyboard.press('Enter');
      },
      () => expect.poll(
        () => captureResult(
          page,
          '{ ids <- rstudioapi::terminalList(); ' +
          'length(ids) > 0 && any(grepl("^2$", rstudioapi::terminalBuffer(ids[[1]]))) }',
        ),
        { timeout: TIMEOUTS.consoleReady },
      ).toBe('TRUE'),
    );

    // Send the terminal contents to a new editor tab.
    await executeCommand(page, 'sendTerminalToEditor');

    // Find the new editor as the active tab (sendTerminalToEditor activates
    // it) and assert it contains both the command and the result "2" on its
    // own line. We can't require any contiguous substring of the command --
    // on Server-on-Linux the prompt ($USER@$HOST:$CWD$ ) pushes the command
    // toward the xterm wrap column, and depending on the prompt length the
    // hard wrap can land anywhere, even mid-word ("...$ exp" / "r 1 + 1" was
    // observed when the cwd was a long sandbox path). That also rules out
    // locating the editor by content marker. So compare with all whitespace
    // and wrap markers (U+00B7 middle dot) stripped, which is invariant
    // under any wrap position, and check the result "2" (a single character,
    // so it can't wrap) on a raw line of its own. The rstudioapi::terminalBuffer ^2$
    // poll above is the authoritative output check; this assertion only
    // confirms the editor tab received both the command and the result.
    const editor = new AceEditor(page, '');
    await expect.poll(
      async () => {
        try {
          const value = (await editor.getValue()).replace(/\r?\n+/g, '\n');
          const dewrapped = value.replace(/[\s\u00B7]+/g, '');
          return dewrapped.includes('expr1+1') && /(?:^|\n)2(?:\n|$)/.test(value);
        } catch {
          return false;
        }
      },
      { timeout: TIMEOUTS.fileOpen },
    ).toBe(true);
  });

  test('toolbar shows next and previous terminal buttons', async ({ rstudioPage: page }) => {
    await killAllTerminals(page);
    await openTerminal(page);

    await expect(page.locator('#rstudio_tb_nextterminal')).toBeVisible();
    await expect(page.locator('#rstudio_tb_previousterminal')).toBeVisible();
  });

  test('R --version runs in the terminal', async ({ rstudioPage: page }) => {
    await killAllTerminals(page);
    await openTerminal(page);

    await retryTerminalInput(
      page,
      async () => {
        await page.keyboard.type('R --version');
        await page.keyboard.press('Enter');
      },
      () => expect.poll(
        () => captureResult(
          page,
          '{ ids <- rstudioapi::terminalList(); ' +
          'length(ids) > 0 && any(grepl("R version", rstudioapi::terminalBuffer(ids[[1]]))) }',
        ),
        { timeout: TIMEOUTS.consoleReady },
      ).toBe('TRUE'),
    );
  });

  test('a file created in the terminal appears in a directory listing', async ({
    rstudioPage: page,
  }) => {
    await killAllTerminals(page);
    await openTerminal(page);

    // cd into the absolute sandbox path first, then create and list the file
    // using a short name. The file is cleaned up by globalTeardown regardless
    // of the terminal's working directory. terminalBuffer() returns one entry
    // per *physical* line, and the echoed command line (prompt + command) can
    // wrap anywhere -- on macOS CI the runner's GUID hostname makes the
    // prompt so long that "ztestfile.txt" was seen torn across a wrap
    // boundary mid-filename. So type the touch argument with a quote split
    // ("ztest""file.txt"), the same trick as expectTerminalRenders: the
    // echoed command then never contains the contiguous filename, and a
    // single intact match can only come from the ls output, which starts at
    // column 0 and cannot wrap. (Requiring the echo too would reintroduce
    // the wrap dependency; this way a match still proves touch succeeded,
    // since ls only lists the file if it exists.)
    const sandboxDir = sandbox.dir.replace(/\\/g, '/');
    await retryTerminalInput(
      page,
      async () => {
        await page.keyboard.type(`cd ${sandboxDir}`);
        await page.keyboard.press('Enter');
        await page.keyboard.type('touch "ztest""file.txt"');
        await page.keyboard.press('Enter');
        await page.keyboard.type('ls');
        await page.keyboard.press('Enter');
      },
      () => expect.poll(
        () => captureResult(
          page,
          '{ ids <- rstudioapi::terminalList(); ' +
          'buf <- rstudioapi::terminalBuffer(ids[[1]]); ' +
          'length(ids) > 0 && any(grepl("ztestfile.txt", buf, fixed = TRUE)) }',
        ),
        { timeout: TIMEOUTS.consoleReady },
      ).toBe('TRUE'),
    );
  });

  test('output reaches the terminal emulator', async ({ rstudioPage: page }) => {
    await killAllTerminals(page);
    await openTerminal(page);

    // Read the client's emulator, not rstudioapi::terminalBuffer(): the
    // server-side buffer receives output even when the client shows nothing.
    // The quotes split the marker, so only the output contains it whole.
    await retryTerminalInput(
      page,
      async () => {
        await page.keyboard.type('echo "pw_""shown"');
        await page.keyboard.press('Enter');
      },
      () => expect.poll(() => renderedTerminalText(page), { timeout: TIMEOUTS.consoleReady })
        .toContain('pw_shown'),
    );
  });

  test('changing the editor theme repaints the terminal in the new colors', async ({ rstudioPage: page }) => {
    // A pref change alone does not re-theme a running session;
    // rstudioapi::applyTheme() does, as Global Options does.
    const applyTheme = (name: string) =>
      executeInConsole(page, `rstudioapi::applyTheme(${rStringLiteral(name)})`, { wait: true });
    const original = (await getPref(page, 'editor_theme')) as string | null;
    await killAllTerminals(page);

    try {
      await applyTheme('Textmate (default)');
      await openTerminal(page);
      await expect.poll(async () => {
        const { drawn, theme } = await terminalBackground(page);
        return drawn.join() === theme.join() && theme.join() !== '0,0,0';
      }, { timeout: TIMEOUTS.consoleReady }).toBe(true);
      const light = (await terminalBackground(page)).theme;

      // The emulator keeps the colors it was created with; the renderer
      // translates them to the new theme's as it draws (ghostty-theme.js).
      // The terminal picks up a theme change after a short delay.
      await applyTheme('Tomorrow Night');
      await focusTerminal(page);
      await expect.poll(async () => {
        const { drawn, theme } = await terminalBackground(page);
        return theme.join() !== light.join() && drawn.join() === theme.join();
      }, { timeout: TIMEOUTS.consoleReady }).toBe(true);
    } finally {
      await applyTheme(original ?? 'Textmate (default)').catch(() => {});
    }
  });

  test(
    'Shift+Backspace deletes the last character before submission',
    { tag: ['@desktop_only'] },
    async ({ rstudioPage: page }) => {
      await killAllTerminals(page);
      await openTerminal(page);

      // Verify the deletion through a filesystem side effect rather than the
      // terminal buffer: type a `touch` command with a stray trailing "Q",
      // delete it with Shift+Backspace, and check which file was created.
      // The buffer is unsuitable for this assertion: after the deletion,
      // readline may redraw the whole (wrapped) prompt line instead of
      // erasing in place, and the server-side buffer capture keeps the stale
      // pre-erase command image, so a grep for the original text matches even
      // though the deletion worked. Whether readline erases or redraws is a
      // shell implementation detail -- the grep started failing with Ubuntu
      // 26.04 (bash 5.3 / readline 8.3, which reworked redisplay) while
      // older Ubuntu erased in place -- and also depends on prompt width,
      // which varies per CI runner (hostname and sandbox path lengths).
      const sandboxDir = sandbox.dir.replace(/\\/g, '/');
      // If Shift+Backspace deleted the trailing "Q", the file without the
      // "Q" exists and the file with it does not. If the keystroke had no
      // effect, only "term_bs_test.txtQ" exists and the first condition
      // stays false; if it deleted more than one character, neither file
      // matches. The file is cleaned up with the sandbox by globalTeardown.
      // A retry cannot hide a Shift+Backspace that does nothing: the "Q"
      // file from the first attempt keeps the second condition false.
      await retryTerminalInput(
        page,
        async () => {
          await page.keyboard.type(`cd ${sandboxDir}`);
          await page.keyboard.press('Enter');
          await page.keyboard.type('touch term_bs_test.txtQ');
          await page.keyboard.press('Shift+Backspace');
          await page.keyboard.press('Enter');
        },
        () => expect.poll(
          () => captureResult(
            page,
            `{ file.exists(file.path(${rStringLiteral(sandboxDir)}, "term_bs_test.txt")) && ` +
            `!file.exists(file.path(${rStringLiteral(sandboxDir)}, "term_bs_test.txtQ")) }`,
          ),
          { timeout: TIMEOUTS.consoleReady },
        ).toBe('TRUE'),
      );
    },
  );
});
