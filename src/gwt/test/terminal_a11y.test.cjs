/*
 * Tests for the terminal's screen reader mirror, using the bundled ghostty-web
 * (libghostty-vt) emulator and a minimal stand-in for the DOM.
 * Run with: node --test src/gwt/test/terminal_a11y.test.cjs
 */

const assert = require("node:assert/strict");
const test = require("node:test");
const terminalPath = "../src/org/rstudio/studio/client/workbench/views/terminal/xterm/";
const { Ghostty, Terminal } = require(terminalPath + "ghostty-web.js");
require(terminalPath + "ghostty-a11y.js");
const { TerminalAccessibility } = globalThis.RStudioTerminalAccessibility;

let ghostty;
test.before(async () => {
   // the module loader resolves its embedded URL against self.location
   globalThis.self ??= globalThis;
   ghostty = await Ghostty.load();
});

/** Just enough of the DOM for the mirror. */
class FakeElement
{
   constructor(doc, tag)
   {
      this.ownerDocument = doc;
      this.tagName = tag;
      this.childNodes = [];
      this.attributes = {};
      this.style = {};
      this.parentNode = null;
      this.textContent = "";
   }
   setAttribute(name, value) { this.attributes[name] = String(value); }
   appendChild(child) { child.parentNode = this; this.childNodes.push(child); return child; }
   removeChild(child)
   {
      this.childNodes.splice(this.childNodes.indexOf(child), 1);
      child.parentNode = null;
      return child;
   }
   get firstChild() { return this.childNodes[0] ?? null; }
   get lastChild() { return this.childNodes[this.childNodes.length - 1] ?? null; }
}

function createDocument()
{
   const doc = { createElement: tag => new FakeElement(doc, tag) };
   return doc;
}

/**
 * A terminal with ghostty's buffer API but no DOM, and its mirror.
 * GHOSTTY_IMP: Terminal.buffer reads the emulator from terminal.wasmTerm.
 */
function createMirror(t, rows = 4, cols = 20)
{
   const term = new Terminal({ cols, rows, ghostty });
   term.wasmTerm = ghostty.createTerminal(cols, rows);
   term.wasmTerm.write("\x1b[2J\x1b[H");
   const container = new FakeElement(createDocument(), "div");
   const mirror = new TerminalAccessibility(term, container, "Terminal 1");
   t.after(() => { mirror.dispose(); term.wasmTerm.free(); });

   const [tree, log] = container.childNodes;
   return {
      mirror,
      write: text => term.wasmTerm.write(text),
      tree: () => tree.childNodes.map(row => row.textContent),
      announced: () => log.childNodes.map(entry => entry.textContent),
      tree_: tree,
      log_: log
   };
}

test("the mirror is a labelled list of rows and a polite log", t => {
   const { tree_, log_, tree } = createMirror(t);
   assert.equal(tree_.attributes.role, "list");
   assert.equal(tree_.attributes["aria-label"], "Terminal 1");
   assert.equal(log_.attributes.role, "log");
   assert.equal(log_.attributes["aria-live"], "polite");
   // visually hidden rather than display: none, which would hide it from
   // screen readers too
   assert.equal(tree_.style.position, "absolute");
   assert.notEqual(tree_.style.display, "none");
   assert.deepEqual(tree(), [" ", " ", " ", " "]);
});

test("the list follows the screen", t => {
   const { mirror, write, tree } = createMirror(t);
   write("$ ls\r\nfile.R\r\n$ ");
   mirror.flush();
   assert.deepEqual(tree(), ["$ ls", "file.R", "$", " "]);
});

test("output is announced line by line once the cursor moves past it", t => {
   const { mirror, write, announced } = createMirror(t);

   // a command being typed is not read keystroke by keystroke
   write("$ ec");
   mirror.flush();
   write("ho hi");
   mirror.flush();
   assert.deepEqual(announced(), []);

   // once submitted, the command line and its output are read
   write("\r\nhi\r\n$ ");
   mirror.flush();
   assert.deepEqual(announced(), ["$ echo hi", "hi"]);
});

test("output that scrolls the screen is announced once", t => {
   const { mirror, write, announced } = createMirror(t, 3);
   write("one\r\ntwo\r\n");
   mirror.flush();
   write("three\r\nfour\r\nfive\r\n");
   mirror.flush();
   assert.deepEqual(announced(), ["one", "two", "three", "four", "five"]);
});

test("a prompt left waiting is announced after a pause", t => {
   const { mirror, write, announced } = createMirror(t);
   write("Password: ");
   mirror.flush();
   assert.deepEqual(announced(), []);

   mirror.flushIdle();
   assert.deepEqual(announced(), ["Password:"]);

   // and not again
   mirror.flush();
   mirror.flushIdle();
   assert.deepEqual(announced(), ["Password:"]);
});

test("switching to a full-screen program announces only later changes", t => {
   const { mirror, write, announced } = createMirror(t);
   write("$ top\r\n");
   mirror.flush();
   const before = announced().length;

   write("\x1b[?1049h\x1b[HPID USER\r\n");
   mirror.flush();
   assert.equal(announced().length, before);
});

test("update() batches output until it settles", async t => {
   const { mirror, write, tree } = createMirror(t);
   write("a\r\n");
   mirror.update();
   write("b\r\n");
   mirror.update();
   assert.deepEqual(tree(), [" ", " ", " ", " "]);
   await new Promise(resolve => setTimeout(resolve, 250));
   assert.deepEqual(tree(), ["a", "b", " ", " "]);
});

test("dispose() removes the mirror", t => {
   const term = new Terminal({ cols: 10, rows: 2, ghostty });
   term.wasmTerm = ghostty.createTerminal(10, 2);
   t.after(() => term.wasmTerm.free());
   const container = new FakeElement(createDocument(), "div");
   const mirror = new TerminalAccessibility(term, container, "Terminal");
   assert.equal(container.childNodes.length, 2);
   mirror.dispose();
   assert.equal(container.childNodes.length, 0);
});
