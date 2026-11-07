/*
 * ghostty-a11y.js
 *
 * Copyright (C) 2026 by Posit Software, PBC
 *
 * Unless you have received this program directly from Posit Software pursuant
 * to the terms of a commercial license agreement with Posit Software, then
 * this program is licensed to you under the terms of version 3 of the
 * GNU Affero General Public License. This program is distributed WITHOUT
 * ANY EXPRESS OR IMPLIED WARRANTY, INCLUDING THOSE OF NON-INFRINGEMENT,
 * MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE. Please refer to the
 * AGPL (http://www.gnu.org/licenses/agpl-3.0.txt) for more details.
 *
 */

// Screen reader support for ghostty-web terminals.
//
// ghostty-web draws the terminal on a canvas, which screen readers cannot
// read, and has no equivalent of xterm.js's screen reader mode. With RStudio's
// screen reader support turned on, this mirrors the terminal into the DOM, as
// that mode did:
//
// - a list of the screen's rows, visually hidden, which a screen reader can
//   move through to review what is on screen; and
// - a polite live region announcing output: each row that changes, once the
//   cursor has left it (so a line being typed is read once it is submitted,
//   not keystroke by keystroke), or once it has been left alone for a moment
//   (so a prompt waiting for input is read too).
//
// The terminal calls update() after it is written to or resized.

(function(root) {
"use strict";

// Wait for output to settle before reading the screen.
var UPDATE_DELAY_MS = 100;

// Announce the cursor's row once it has been left alone this long.
var IDLE_DELAY_MS = 1000;

// Bound what one update announces, and what the live region keeps.
var MAX_ANNOUNCED_LINES = 20;
var MAX_LOG_ENTRIES = 50;

function hide(element)
{
   // visually hidden, but present for assistive technology
   var style = element.style;
   style.position = "absolute";
   style.width = "1px";
   style.height = "1px";
   style.overflow = "hidden";
   style.clip = "rect(0 0 0 0)";
   style.clipPath = "inset(50%)";
   style.whiteSpace = "pre";
}

// The text of a row of a ghostty buffer: blank cells as spaces, the trailing
// half of a wide character omitted, trailing blanks trimmed.
function rowText(line)
{
   if (!line)
      return "";

   var text = "";
   for (var i = 0; i < line.length; i++)
   {
      var cell = line.getCell(i);
      if (cell && cell.getWidth() !== 0)
         text += cell.getChars() || " ";
   }
   return text.replace(/\s+$/, "");
}

// The screen's rows, top to bottom, and how many rows of scrollback sit above
// them. The alternate screen has no scrollback.
function readScreen(term)
{
   var buffer = term.buffer.active;
   var top = Math.max(0, buffer.length - term.rows);
   var rows = [];
   for (var y = top; y < buffer.length; y++)
      rows.push(rowText(buffer.getLine(y)));
   return { rows: rows, top: top, alternate: buffer.type === "alternate" };
}

function TerminalAccessibility(term, container, label)
{
   var doc = container.ownerDocument;
   this._term = term;
   this._timer = null;
   this._idleTimer = null;
   this._screen = null;
   this._pending = {};

   var tree = doc.createElement("div");
   tree.setAttribute("role", "list");
   tree.setAttribute("aria-label", label);
   tree.className = "xterm-rstudio-a11y-tree";
   hide(tree);
   this._tree = tree;

   var log = doc.createElement("div");
   log.setAttribute("role", "log");
   log.setAttribute("aria-live", "polite");
   log.setAttribute("aria-relevant", "additions");
   log.className = "xterm-rstudio-a11y-log";
   hide(log);
   this._log = log;

   container.appendChild(tree);
   container.appendChild(log);

   this._screen = readScreen(term);
   this._renderTree(this._screen.rows);
}

TerminalAccessibility.prototype.update = function()
{
   var self = this;
   if (this._timer !== null)
      return;

   this._timer = setTimeout(function() {
      self._timer = null;
      self.flush();
   }, UPDATE_DELAY_MS);
};

// Bring the mirror up to date with the terminal now.
TerminalAccessibility.prototype.flush = function()
{
   if (this._timer !== null)
   {
      clearTimeout(this._timer);
      this._timer = null;
   }
   this._cancelIdle();

   var previous = this._screen;
   var screen = readScreen(this._term);
   this._screen = screen;
   this._renderTree(screen.rows);

   // Rows are compared by their position in the whole buffer, so output that
   // scrolls the screen is not mistaken for changes to every row. Switching
   // to or from the alternate screen (a full-screen program starting or
   // ending) changes everything; announce nothing for it but what changes
   // afterwards.
   var announce = [];
   if (previous && previous.alternate === screen.alternate)
   {
      // from the first row shown last time to the end of the buffer, which
      // includes rows that have scrolled off the screen since
      var buffer = this._term.buffer.active;
      var cursor = screen.top + buffer.cursorY;
      var end = screen.top + screen.rows.length;

      for (var key = Math.min(previous.top, screen.top); key < end; key++)
      {
         var text = key >= screen.top ? screen.rows[key - screen.top] : rowText(buffer.getLine(key));
         var before = previous.rows[key - previous.top];
         var changed = before === undefined ? text.length > 0 : before !== text;

         // a row is announced once it stops changing: hold the cursor's row
         // (a line still being typed or printed) until the cursor moves on
         if (changed)
            this._pending[key] = true;
         if (this._pending[key] && key !== cursor)
         {
            delete this._pending[key];
            if (text.length > 0)
               announce.push(text);
         }
      }
   }
   else
   {
      this._pending = {};
   }

   this._announce(announce);

   for (var pending in this._pending)
   {
      if (Object.prototype.hasOwnProperty.call(this._pending, pending))
      {
         this._scheduleIdle();
         break;
      }
   }
};

// Announce the rows still waiting -- in practice the cursor's -- if nothing
// has changed since they were last read.
TerminalAccessibility.prototype.flushIdle = function()
{
   this._cancelIdle();
   var screen = readScreen(this._term);
   if (!this._screen || screen.top !== this._screen.top || screen.alternate !== this._screen.alternate)
      return;

   var announce = [];
   for (var i = 0; i < screen.rows.length; i++)
   {
      var key = screen.top + i;
      if (!this._pending[key] || screen.rows[i] !== this._screen.rows[i])
         continue;
      delete this._pending[key];
      if (screen.rows[i].length > 0)
         announce.push(screen.rows[i]);
   }
   this._announce(announce);
};

TerminalAccessibility.prototype._scheduleIdle = function()
{
   var self = this;
   this._idleTimer = setTimeout(function() {
      self._idleTimer = null;
      self.flushIdle();
   }, IDLE_DELAY_MS);
};

TerminalAccessibility.prototype._cancelIdle = function()
{
   if (this._idleTimer !== null)
      clearTimeout(this._idleTimer);
   this._idleTimer = null;
};

TerminalAccessibility.prototype._announce = function(lines)
{
   if (lines.length > MAX_ANNOUNCED_LINES)
      lines = lines.slice(lines.length - MAX_ANNOUNCED_LINES);
   for (var i = 0; i < lines.length; i++)
      this._appendLog(lines[i]);
};

TerminalAccessibility.prototype._renderTree = function(rows)
{
   var tree = this._tree;
   var doc = tree.ownerDocument;
   while (tree.childNodes.length > rows.length)
      tree.removeChild(tree.lastChild);
   while (tree.childNodes.length < rows.length)
   {
      var item = doc.createElement("div");
      item.setAttribute("role", "listitem");
      tree.appendChild(item);
   }
   for (var i = 0; i < rows.length; i++)
   {
      // a blank row is read as such rather than skipped
      var text = rows[i].length > 0 ? rows[i] : " ";
      if (tree.childNodes[i].textContent !== text)
         tree.childNodes[i].textContent = text;
   }
};

TerminalAccessibility.prototype._appendLog = function(text)
{
   var log = this._log;
   var entry = log.ownerDocument.createElement("div");
   entry.textContent = text;
   log.appendChild(entry);
   while (log.childNodes.length > MAX_LOG_ENTRIES)
      log.removeChild(log.firstChild);
};

TerminalAccessibility.prototype.dispose = function()
{
   if (this._timer !== null)
      clearTimeout(this._timer);
   this._timer = null;
   this._cancelIdle();
   if (this._tree.parentNode)
      this._tree.parentNode.removeChild(this._tree);
   if (this._log.parentNode)
      this._log.parentNode.removeChild(this._log);
};

root.RStudioTerminalAccessibility = {
   TerminalAccessibility: TerminalAccessibility,
   rowText: rowText
};

})(typeof window !== "undefined" ? window : globalThis);
