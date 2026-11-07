/*
 * Regression tests for terminal file links, using the bundled ghostty-web
 * (libghostty-vt) buffer.
 * Run with: node --test src/gwt/test/terminal_file_links.test.cjs
 */

const assert = require("node:assert/strict");
const test = require("node:test");
const terminalPath = "../src/org/rstudio/studio/client/workbench/views/terminal/xterm/";
const { Ghostty, Terminal } = require(terminalPath + "ghostty-web.js");
require(terminalPath + "file-links.js");
const { FileLinkProvider } = globalThis.RStudioFileLinks;

let ghostty;
test.before(async () => {
   // the module loader resolves its embedded URL against self.location
   globalThis.self ??= globalThis;
   ghostty = await Ghostty.load();
});

/**
 * A terminal with ghostty's buffer API but no DOM: open() needs a canvas, so
 * the emulator is attached directly. GHOSTTY_IMP: Terminal.buffer reads the
 * emulator from terminal.wasmTerm.
 */
function createTerminal(t, text, cols = 80)
{
   const terminal = new Terminal({ cols, rows: 10, ghostty });
   terminal.wasmTerm = ghostty.createTerminal(cols, 10);
   t.after(() => terminal.wasmTerm.free());

   // as XTermNative.clearNewEmulator() does: an emulator created after a
   // narrower one was freed otherwise shows leftover memory in blank cells
   write(terminal, "\x1b[2J\x1b[H");
   write(terminal, text);
   return terminal;
}

function write(terminal, text)
{
   terminal.wasmTerm.write(text);
}

/**
 * Hold or release the open-link modifier. Its state is shared by every
 * terminal, so it is released again once the test ends.
 */
function holdModifier(t, events, held = true)
{
   events.keydown({ ctrlKey: held });
   t.after(() => events.keyup({}));
}

/**
 * A stand-in terminal exposing a real terminal's buffer plus the DOM hooks the
 * provider listens on, so a test can deliver key and mouse events to it.
 */
function withEventHooks(terminal)
{
   const events = {};
   const listen = (type, handler) => { events[type] = handler; };
   return {
      cols: terminal.cols,
      buffer: terminal.buffer,
      element: {
         addEventListener: listen,
         ownerDocument: { addEventListener: listen, defaultView: { addEventListener: listen } }
      },
      events
   };
}

/**
 * A provider for `terminal` with the modifier held, as it is whenever ghostty
 * asks for links worth resolving.
 */
function createProvider(t, terminal, host)
{
   const view = withEventHooks(terminal);
   const provider = new FileLinkProvider(view, host);
   t.after(() => provider.dispose());
   holdModifier(t, view.events);
   return provider;
}

function activate(links)
{
   assert.equal(links.length, 1);
   links[0].activate({ button: 0, ctrlKey: true });
}

test("a cwd change discards pending links and their cache entries", t => {
   const terminal = createTerminal(t, "file.R");
   const requests = [];
   const opened = [];
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => requests.push(callback),
      open: path => opened.push(path)
   });

   let stale = "pending";
   provider.provideLinks(0, links => { stale = links; });
   provider.clearCache();
   requests[0](["/old/file.R"]);
   assert.equal(stale, undefined);

   provider.provideLinks(0, activate);
   assert.equal(requests.length, 2);
   requests[1](["/new/file.R"]);
   assert.deepEqual(opened, ["/new/file.R"]);
});

test("every request is answered, even for an empty row", t => {
   const terminal = createTerminal(t, "file.R\r\n");
   let resolve;
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => { resolve = callback; }
   });

   let first;
   provider.provideLinks(0, links => { first = links; });

   let emptyAnswered = false;
   provider.provideLinks(1, links => {
      emptyAnswered = true;
      assert.equal(links, undefined);
   });
   assert.equal(emptyAnswered, true);

   // ghostty caches links per row, so a reply for a row the mouse has since
   // left is still delivered
   resolve(["/cwd/file.R"]);
   assert.equal(first.length, 1);
});

test("a late reply from the previous cwd cannot overwrite a fresh resolution", t => {
   const terminal = createTerminal(t, "file.R");
   const requests = [];
   const opened = [];
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => requests.push(callback),
      open: path => opened.push(path)
   });

   provider.provideLinks(0, links => assert.equal(links, undefined));
   provider.clearCache();
   provider.provideLinks(0, activate);
   requests[1](["/new/file.R"]);
   requests[0](["/old/file.R"]);

   provider.provideLinks(0, activate);
   assert.equal(requests.length, 2);
   assert.deepEqual(opened, ["/new/file.R", "/new/file.R"]);
});

for (const row of [0, 1, 2])
{
   test(`a quoted path spanning three rows resolves when hovering row ${row}`, t => {
      const path = "dir with spaces/and more/file name.R";
      const terminal = createTerminal(t, '"' + path + '"', 16);
      assert.equal(terminal.buffer.active.getLine(2).isWrapped, true);
      const opened = [];
      const provider = createProvider(t, terminal, {
         resolve: (paths, callback) => {
            assert.deepEqual(paths, [path]);
            callback(["/cwd/" + path]);
         },
         open: resolved => opened.push(resolved)
      });

      let delivered = false;
      provider.provideLinks(row, links => {
         delivered = true;
         assert.equal(links.length, 1);
         assert.equal(links[0].text, path);
         assert.deepEqual(links[0].range, {
            start: { x: 1, y: 0 },
            end: { x: path.length % 16, y: 2 }
         });
         activate(links);
      });
      assert.equal(delivered, true);
      assert.deepEqual(opened, ["/cwd/" + path]);
   });
}

test("a path after a run of blank cells maps to the right columns", t => {
   const terminal = createTerminal(t, "a\x1b[10Gfile.R");
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => callback(paths.map(p => p === "file.R" ? "/cwd/file.R" : ""))
   });

   let links;
   provider.provideLinks(0, result => { links = result; });
   assert.equal(links.length, 1);
   assert.deepEqual(links[0].range, { start: { x: 9, y: 0 }, end: { x: 14, y: 0 } });
});

test("rewritten terminal output discards a pending link response", t => {
   const terminal = createTerminal(t, "old.R");
   const requests = [];
   const opened = [];
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => requests.push(callback),
      open: path => opened.push(path)
   });

   let stale = "pending";
   provider.provideLinks(0, links => { stale = links; });
   write(terminal, "\rnew.R");
   requests[0](["/cwd/old.R"]);
   assert.equal(stale, undefined);

   provider.provideLinks(0, activate);
   requests[1](["/cwd/new.R"]);
   assert.deepEqual(opened, ["/cwd/new.R"]);
});

test("switching terminal buffers discards a pending link response", t => {
   const terminal = createTerminal(t, "file.R");
   let resolve;
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => { resolve = callback; }
   });
   let stale = "pending";
   provider.provideLinks(0, links => { stale = links; });
   write(terminal, "\x1b[?1049hfile.R");
   resolve(["/cwd/file.R"]);
   assert.equal(stale, undefined);
});

test("a link delivered under a previous cwd is resolved again when clicked", t => {
   const terminal = createTerminal(t, "file.R");
   const requests = [];
   const opened = [];
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => requests.push({ paths, callback }),
      open: path => opened.push(path)
   });
   let delivered;
   provider.provideLinks(0, links => { delivered = links; });
   requests[0].callback(["/old/file.R"]);

   // the terminal's cwd changes between the hover and the click
   provider.clearCache();
   activate(delivered);
   assert.deepEqual(opened, []);
   assert.equal(requests.length, 2);
   assert.deepEqual(requests[1].paths, ["file.R"]);

   requests[1].callback(["/new/file.R"]);
   assert.deepEqual(opened, ["/new/file.R"]);
});

test("a stale link whose text no longer names a file opens nothing", t => {
   const terminal = createTerminal(t, "file.R");
   const replies = [["/old/file.R"], [""]];
   const opened = [];
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => callback(replies.shift()),
      open: path => opened.push(path)
   });
   let delivered;
   provider.provideLinks(0, links => { delivered = links; });
   provider.clearCache();
   activate(delivered);
   assert.deepEqual(opened, []);
   assert.equal(replies.length, 0);
});

test("no links are offered, or resolved, while the modifier is up", t => {
   const terminal = createTerminal(t, "file.R");
   const view = withEventHooks(terminal);
   let resolves = 0;
   const provider = new FileLinkProvider(view, {
      resolve: (paths, callback) => { resolves++; callback(["/cwd/file.R"]); }
   });
   t.after(() => provider.dispose());

   let answered = false;
   provider.provideLinks(0, links => {
      answered = true;
      assert.equal(links, undefined);
   });
   assert.equal(answered, true);
   assert.equal(resolves, 0);

   holdModifier(t, view.events);
   provider.provideLinks(0, links => assert.equal(links.length, 1));
   assert.equal(resolves, 1);
});

test("hosts hear when the modifier is pressed and released", t => {
   const terminal = createTerminal(t, "file.R");
   const view = withEventHooks(terminal);
   const changes = [];
   const provider = new FileLinkProvider(view, {
      resolve: () => {},
      modifierChanged: held => changes.push(held)
   });
   t.after(() => view.events.keyup({}));

   view.events.keydown({ ctrlKey: true });
   view.events.keydown({ ctrlKey: true });
   view.events.keyup({});
   assert.deepEqual(changes, [true, false]);

   // the mouse reports a modifier pressed while the document was unfocused,
   // and a release in another window arrives only as a blur
   view.events.mousemove({ ctrlKey: true });
   view.events.blur();
   assert.deepEqual(changes, [true, false, true, false]);

   // a disposed provider no longer hears about it
   provider.dispose();
   view.events.keydown({ ctrlKey: true });
   assert.deepEqual(changes, [true, false, true, false]);
});

/**
 * Resolve the single link on the first row of `text`, recording the host's
 * hover notifications.
 */
function createLink(t, text = "file.R")
{
   const terminal = createTerminal(t, text);
   const opened = [];
   const hovers = [];
   const provider = createProvider(t, terminal, {
      resolve: (paths, callback) => callback(paths.map(path => "/cwd/" + path)),
      open: path => opened.push(path),
      hover: path => hovers.push(path),
      leave: () => hovers.push(null)
   });

   let links;
   provider.provideLinks(0, result => { links = result; });
   assert.equal(links.length, 1);
   return { link: links[0], provider, opened, hovers };
}

test("the host is told when a link is hovered and left", t => {
   const { link, hovers } = createLink(t);
   link.hover(true);
   link.hover(false);
   // leaving a link that is not hovered is not reported again
   link.hover(false);
   assert.deepEqual(hovers, ["/cwd/file.R", null]);
});

test("a terminal torn down mid-hover releases only its own link", t => {
   const first = createLink(t);
   const second = createLink(t, "other.R");
   second.link.hover(true);

   first.provider.dispose();
   assert.deepEqual(first.hovers, []);
   assert.deepEqual(second.hovers, ["/cwd/other.R"]);

   second.provider.dispose();
   assert.deepEqual(second.hovers, ["/cwd/other.R", null]);
});

test("a click without the modifier does not open the file", t => {
   const { link, opened } = createLink(t);

   link.activate({ button: 0 });
   assert.deepEqual(opened, []);

   link.activate({ button: 0, ctrlKey: true });
   assert.deepEqual(opened, ["/cwd/file.R"]);
});
