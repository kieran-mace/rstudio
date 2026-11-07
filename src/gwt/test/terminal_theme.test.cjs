/*
 * Tests for terminal theme changes, using the bundled ghostty-web
 * (libghostty-vt) emulator.
 * Run with: node --test src/gwt/test/terminal_theme.test.cjs
 */

const assert = require("node:assert/strict");
const test = require("node:test");
const terminalPath = "../src/org/rstudio/studio/client/workbench/views/terminal/xterm/";
const { Ghostty, Terminal } = require(terminalPath + "ghostty-web.js");
require(terminalPath + "ghostty-theme.js");
const { ThemeTracker, forEmulator, buildColorMaps, remapCells, parseColor } = globalThis.RStudioTerminalTheme;

let ghostty;
test.before(async () => {
   // the module loader resolves its embedded URL against self.location
   globalThis.self ??= globalThis;
   ghostty = await Ghostty.load();
});

const NAMES = [
   "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
   "brightBlack", "brightRed", "brightGreen", "brightYellow",
   "brightBlue", "brightMagenta", "brightCyan", "brightWhite"
];

// A theme as XTermTheme builds one: colors read from CSS, as rgb().
function theme(foreground, background, palette)
{
   const result = { foreground, background, cursor: foreground };
   NAMES.forEach((name, i) => { result[name] = palette[i]; });
   return result;
}

const rgb = (r, g, b) => `rgb(${r}, ${g}, ${b})`;
const LIGHT = theme(rgb(0, 0, 0), rgb(255, 255, 255),
   NAMES.map((_, i) => i === 0 ? rgb(0, 0, 0) : rgb(i * 10, i * 5, 200 - i)));
const DARK = theme(rgb(220, 220, 220), rgb(30, 30, 30),
   NAMES.map((_, i) => rgb(100 + i, 50 + i * 3, i * 7)));

/**
 * An emulator configured as XTermNative.createTerminal() configures one:
 * GHOSTTY_IMP, Terminal.buildWasmConfig() turns the options into the
 * emulator's configuration.
 */
function createEmulator(t, base)
{
   const config = new Terminal({ ghostty, theme: forEmulator(base) }).buildWasmConfig();
   const emulator = ghostty.createTerminal(40, 4, config);
   t.after(() => emulator.free());
   emulator.write("\x1b[2J\x1b[H");
   return emulator;
}

const colorOf = (cell, which) => (cell[which + "_r"] << 16) | (cell[which + "_g"] << 8) | cell[which + "_b"];

test("colors parse from the forms themes use", () => {
   assert.equal(parseColor("rgb(1, 2, 3)"), 0x010203);
   assert.equal(parseColor("rgba(1, 2, 3, 0.3)"), 0x010203);
   assert.equal(parseColor("#abc"), 0xaabbcc);
   assert.equal(parseColor("#A0B1C2"), 0xa0b1c2);
   assert.equal(parseColor("transparent"), null);
   assert.equal(parseColor(undefined), null);
});

test("the emulator is given a black it uses rather than its own default", t => {
   assert.equal(forEmulator(LIGHT).black, "#000001");
   assert.equal(forEmulator(LIGHT).red, "#0a05c7");

   // ghostty would read 0 (black) as "use the built-in default"
   const emulator = createEmulator(t, LIGHT);
   emulator.write("\x1b[30mK\x1b[0mD");
   const cells = emulator.getLine(0);
   assert.equal(colorOf(cells[0], "fg"), 0x000001);
   assert.equal(colorOf(cells[1], "fg"), 0x000001);
   assert.equal(colorOf(cells[1], "bg"), 0xffffff);
});

test("output already shown is drawn in the colors of a new theme", t => {
   const emulator = createEmulator(t, LIGHT);
   // default text, red, bright blue, black on the default background, text
   // on a cyan background, a 256-color and a true-color cell
   emulator.write("D\x1b[31mR\x1b[94mB\x1b[30mK\x1b[0m\x1b[46mC\x1b[0m\x1b[38;5;200mX\x1b[38;2;1;2;3mT\x1b[0m");

   const maps = buildColorMaps(LIGHT, DARK);
   const cells = emulator.getLine(0);
   const x256 = colorOf(cells[5], "fg");
   remapCells(cells, maps);

   const dark = name => parseColor(DARK[name]);
   assert.equal(colorOf(cells[0], "fg"), dark("foreground"));
   assert.equal(colorOf(cells[0], "bg"), dark("background"));
   assert.equal(colorOf(cells[1], "fg"), dark("red"));
   assert.equal(colorOf(cells[2], "fg"), dark("brightBlue"));
   // black is also the default foreground in LIGHT: as a foreground it follows
   // the new default foreground
   assert.equal(colorOf(cells[3], "fg"), dark("foreground"));
   assert.equal(colorOf(cells[4], "bg"), dark("cyan"));
   assert.equal(colorOf(cells[5], "fg"), x256);
   assert.equal(colorOf(cells[6], "fg"), 0x010203);

   // blank cells, and the scrollback, follow too
   assert.equal(colorOf(cells[30], "bg"), dark("background"));
   for (let i = 0; i < 10; i++)
      emulator.write("\r\n");
   const scrolled = emulator.getScrollbackLine(0);
   remapCells(scrolled, maps);
   assert.equal(colorOf(scrolled[1], "fg"), dark("red"));
});

test("switching back to the creation theme restores its colors", t => {
   assert.equal(buildColorMaps(LIGHT, LIGHT), null);

   const emulator = createEmulator(t, DARK);
   emulator.write("\x1b[31mR");
   const drawn = [];
   const renderer = {
      renderLine(cells) { drawn.push(colorOf(cells[0], "fg")); },
      setTheme() {}
   };
   const tracker = new ThemeTracker(renderer, DARK);

   tracker.setTheme(LIGHT);
   renderer.renderLine(emulator.getLine(0), 0, 40);
   tracker.setTheme(DARK);
   renderer.renderLine(emulator.getLine(0), 0, 40);

   assert.deepEqual(drawn, [parseColor(LIGHT.red), parseColor(DARK.red)]);
});

test("the tracker hands the renderer the new theme and draws through it", () => {
   const calls = [];
   const renderer = {
      renderLine(cells, row, cols) { calls.push(["renderLine", colorOf(cells[0], "fg"), row, cols]); },
      setTheme(next) { calls.push(["setTheme", next]); }
   };
   const tracker = new ThemeTracker(renderer, LIGHT);

   const red = parseColor(forEmulator(LIGHT).red);
   const cell = () => [{ fg_r: red >> 16, fg_g: (red >> 8) & 255, fg_b: red & 255, bg_r: 255, bg_g: 255, bg_b: 255 }];

   renderer.renderLine(cell(), 0, 1);
   tracker.setTheme(DARK);
   renderer.renderLine(cell(), 1, 1);

   assert.deepEqual(calls, [
      ["renderLine", red, 0, 1],
      ["setTheme", DARK],
      ["renderLine", parseColor(DARK.red), 1, 1]
   ]);
});
