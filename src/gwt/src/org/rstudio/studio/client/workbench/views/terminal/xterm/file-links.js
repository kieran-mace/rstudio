/*
 * file-links.js
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

// A ghostty-web link provider that turns file paths printed in the terminal
// (git status output, compiler diagnostics, ls listings, ...) into links that
// open the file in RStudio with Ctrl+Click (Cmd+Click on macOS).
//
// Detection is deliberately loose: every whitespace-delimited token on the
// hovered line is a candidate, and the host decides which of them name an
// existing file relative to the terminal's working directory. Only those
// become links, so plain words never get underlined.
//
// ghostty-web's link API follows xterm.js's, with these differences (read
// from ghostty-web 0.4.0 -- the version pinned in src/gwt/tools/build-ghostty;
// re-check them, marked GHOSTTY_IMP, when it is upgraded):
//
// - rows passed to provideLinks() and link ranges are 0-based, and a range's
//   end column is inclusive;
// - a link is told about the pointer through hover(isHovered);
// - every hovered link is underlined, with no per-link decorations;
// - the links a provider returns for a row are cached until the terminal is
//   next written to, and the provider must answer every request (rows are
//   scanned one provider at a time, awaiting each reply).
//
// The wrapped-line and string-to-cell mapping logic mirrors LinkComputer in
// xterm's web-links addon (MIT licensed, https://github.com/xtermjs/xterm.js).

(function(root) {
"use strict";

// Longest run of wrapped rows to stitch together, in characters.
var MAX_LINE_CHARS = 2048;

// Bound the work sent to the host for one line.
var MAX_CANDIDATES = 64;
var MAX_CANDIDATE_LENGTH = 512;

// Resolved lines are remembered briefly so sweeping the mouse over the same
// output, or releasing and pressing the modifier again, does not re-query
// the host.
var CACHE_TTL_MS = 5000;
var CACHE_MAX_ENTRIES = 64;

// Characters that never belong to an unquoted path token.
var TOKEN_PATTERN = /[^\s"'`<>|]+/g;

// Quoted tokens may contain spaces: git prints `rename "a b.R" -> "c.R"`.
var QUOTED_PATTERN = /"([^"\s][^"]*)"|'([^'\s][^']*)'/g;

var LEADING_JUNK = /^[(\[{<]+/;
var TRAILING_PUNCTUATION = /[.,;:!?]$/;

// Position suffixes: gcc/cli style `file:12:3`, MSVC style `file(12,3)`,
// and the `file#12` form R uses when printing srcrefs.
var POSITION_PATTERNS = [
   /^(.+?):(\d+)(?::(\d+))?$/,
   /^(.+?)\((\d+)(?:,\s*(\d+))?\)$/,
   /^(.+?)#(\d+)$/
];

var CLOSERS = { ")": "(", "]": "[", "}": "{", ">": "<" };

// File links only exist -- and so are only underlined, and only activate --
// while the platform's open-link modifier is held, so hovering ordinary
// output does not light up every word that happens to name a file. ghostty
// underlines whatever link is hovered, so instead of decorating links on and
// off, a provider offers none while the modifier is up, and each provider's
// host is told when the modifier changes so it can have the hovered row
// scanned again. The state is shared by every terminal in the document.
var modifier = {
   isMac: false,
   held: false,
   providers: []
};

function hasModifier(event)
{
   return modifier.isMac ? !!event.metaKey : !!event.ctrlKey;
}

function setModifierHeld(held)
{
   if (modifier.held === held)
      return;

   modifier.held = held;

   // copy: a host may tear its terminal (and so its provider) down in reply
   var providers = modifier.providers.slice();
   for (var i = 0; i < providers.length; i++)
   {
      var host = providers[i]._host;
      if (host.modifierChanged)
         host.modifierChanged(held);
   }
}

// Watch the modifier, so a hovered link lights up as soon as it is pressed and
// goes dark when it is released. Key events only arrive while this document
// has focus, so the terminal's own mouse events -- which carry the modifier
// state -- are consulted as well; that also covers moving into the terminal
// with the modifier already down.
function trackModifier(element, isMac)
{
   modifier.isMac = isMac;

   if (element)
   {
      element.addEventListener("mousemove", function(event) {
         setModifierHeld(hasModifier(event));
      }, true);
   }

   // the key listeners are shared by every terminal in the document
   var ownerDocument = element && element.ownerDocument;
   if (!ownerDocument || ownerDocument.rstudioFileLinkModifier_)
      return;

   ownerDocument.rstudioFileLinkModifier_ = true;
   ownerDocument.addEventListener("keydown", function(event) {
      setModifierHeld(hasModifier(event));
   }, true);
   ownerDocument.addEventListener("keyup", function(event) {
      setModifierHeld(hasModifier(event));
   }, true);

   // a release that happens while another window has focus is never delivered
   var view = ownerDocument.defaultView;
   if (view)
      view.addEventListener("blur", function() { setModifierHeld(false); });
}

function FileLinkProvider(terminal, host)
{
   this._terminal = terminal;
   this._host = host;
   this._cacheGeneration = 0;
   this._cache = {};
   this._cacheKeys = [];
   this._hovered = null;

   modifier.providers.push(this);
   trackModifier(terminal.element, !!host.isMac);
}

// GHOSTTY_IMP: `row` is 0-based, and `callback` must be called exactly once.
FileLinkProvider.prototype.provideLinks = function(row, callback)
{
   if (!modifier.held)
   {
      callback(undefined);
      return;
   }

   var terminal = this._terminal;
   var buffer = terminal.buffer.active;
   var window = getWindowedLineStrings(terminal, row);
   var text = window.lines.join("");
   var matches = findCandidates(text);
   if (matches.length === 0)
   {
      callback(undefined);
      return;
   }

   var self = this;
   var cached = this._lookupCache(text);
   if (cached)
   {
      callback(self._buildLinks(window.startLine, matches, cached));
      return;
   }

   var candidates = matches.map(function(match) { return match.path; });
   var cacheGeneration = this._cacheGeneration;
   this._host.resolve(candidates, function(resolved) {
      // A cwd change invalidates pending resolutions as well as cached ones.
      if (cacheGeneration !== self._cacheGeneration)
      {
         callback(undefined);
         return;
      }

      resolved = resolved || [];
      self._storeCache(text, resolved);

      // The result can be cached by text, but its offsets only apply while
      // the captured rows still contain that text in the same buffer.
      if (terminal.buffer.active !== buffer || !sameWindow(window, getWindowedLineStrings(terminal, row)))
      {
         callback(undefined);
         return;
      }

      callback(self._buildLinks(window.startLine, matches, resolved));
   });
};

FileLinkProvider.prototype._buildLinks = function(startLine, matches, resolved)
{
   var links = [];
   for (var i = 0; i < matches.length; i++)
   {
      var path = resolved[i];
      if (!path)
         continue;

      var range = computeRange(this._terminal, startLine, matches[i].index, matches[i].length);
      if (range)
         links.push(this._createLink(range, matches[i], path));
   }
   return links.length > 0 ? links : undefined;
};

FileLinkProvider.prototype._createLink = function(range, match, path)
{
   var self = this;
   var cacheGeneration = this._cacheGeneration;
   var host = this._host;
   var link = {
      range: range,
      text: match.text,
      activate: function(event) {
         if (event.button !== 0 || !hasModifier(event))
            return;

         // The path was resolved against the cwd of the hover. If the cwd
         // has changed since (the first report lands a couple of seconds
         // after the shell starts), resolve the text again rather than open
         // a stale path or drop the click with nothing to show for it.
         if (cacheGeneration === self._cacheGeneration)
         {
            host.open(path, match.line, match.column);
            return;
         }

         host.resolve([match.path], function(resolved) {
            var fresh = resolved && resolved[0];
            if (fresh)
               host.open(fresh, match.line, match.column);
         });
      },
      // GHOSTTY_IMP: one call for both the pointer arriving and leaving
      hover: function(isHovered) {
         if (isHovered)
         {
            self._hovered = link;
            if (host.hover)
               host.hover(path);
         }
         else if (self._hovered === link)
         {
            self._hovered = null;
            if (host.leave)
               host.leave();
         }
      }
   };

   return link;
};

// A terminal can be torn down with a link still hovered: an element detached
// from the document gets no mouseleave, so the link is never told the pointer
// left. Let go of the hover, and stop hearing about the modifier, so the dead
// terminal is not kept alive.
FileLinkProvider.prototype.dispose = function()
{
   if (this._hovered)
   {
      this._hovered = null;
      if (this._host.leave)
         this._host.leave();
   }

   var index = modifier.providers.indexOf(this);
   if (index !== -1)
      modifier.providers.splice(index, 1);
};

FileLinkProvider.prototype.clearCache = function()
{
   this._cacheGeneration++;
   this._cache = {};
   this._cacheKeys = [];
};

FileLinkProvider.prototype._lookupCache = function(text)
{
   var entry = this._cache[text];
   if (!entry)
      return null;

   if (Date.now() - entry.time > CACHE_TTL_MS)
   {
      delete this._cache[text];
      var stale = this._cacheKeys.indexOf(text);
      if (stale !== -1)
         this._cacheKeys.splice(stale, 1);
      return null;
   }
   return entry.resolved;
};

FileLinkProvider.prototype._storeCache = function(text, resolved)
{
   if (!this._cache[text])
   {
      this._cacheKeys.push(text);
      while (this._cacheKeys.length > CACHE_MAX_ENTRIES)
         delete this._cache[this._cacheKeys.shift()];
   }
   this._cache[text] = { time: Date.now(), resolved: resolved };
};

function sameWindow(a, b)
{
   return a.startLine === b.startLine &&
          a.lines.length === b.lines.length &&
          a.lines.every(function(line, index) { return line === b.lines[index]; });
}

// Split a line into candidate tokens. Each candidate records where it sits in
// the line (so it can be mapped back to buffer cells), the path to validate,
// and any line/column suffix.
function findCandidates(text)
{
   var candidates = [];
   var masked = text;
   var match;

   QUOTED_PATTERN.lastIndex = 0;
   while ((match = QUOTED_PATTERN.exec(text)) !== null)
   {
      var quoted = match[1] !== undefined ? match[1] : match[2];
      addCandidate(candidates, match.index + 1, quoted);

      // blank out the quoted region so the unquoted pass skips it
      masked = masked.substring(0, match.index) +
               repeatSpace(match[0].length) +
               masked.substring(match.index + match[0].length);
   }

   TOKEN_PATTERN.lastIndex = 0;
   while ((match = TOKEN_PATTERN.exec(masked)) !== null)
   {
      var trimmed = trimToken(match[0]);
      if (trimmed.text.length > 0)
         addCandidate(candidates, match.index + trimmed.offset, trimmed.text);
   }

   candidates.sort(function(a, b) { return a.index - b.index; });
   return candidates.slice(0, MAX_CANDIDATES);
}

function addCandidate(candidates, index, text)
{
   if (text.length > MAX_CANDIDATE_LENGTH)
      return;

   // URLs belong to the web links addon; bare numbers and punctuation-only
   // tokens (`->`, `...`) are never paths
   if (text.indexOf("://") !== -1 || !/[A-Za-z0-9]/.test(text) || /^\d+$/.test(text))
      return;

   var position = parsePosition(text);
   candidates.push({
      index: index,
      length: text.length,
      text: text,
      path: position.path,
      line: position.line,
      column: position.column
   });
}

// Strip enclosing brackets and sentence punctuation from a token, returning
// the kept text and its offset within the original token.
function trimToken(token)
{
   var offset = 0;
   var leading = LEADING_JUNK.exec(token);
   if (leading)
   {
      offset = leading[0].length;
      token = token.substring(offset);
   }

   for (;;)
   {
      if (TRAILING_PUNCTUATION.test(token))
      {
         token = token.substring(0, token.length - 1);
         continue;
      }

      var last = token.charAt(token.length - 1);
      var opener = CLOSERS[last];
      if (opener && token.indexOf(opener) === -1)
      {
         token = token.substring(0, token.length - 1);
         continue;
      }

      break;
   }

   return { text: token, offset: offset };
}

function parsePosition(text)
{
   for (var i = 0; i < POSITION_PATTERNS.length; i++)
   {
      var match = POSITION_PATTERNS[i].exec(text);
      if (match)
      {
         return {
            path: match[1],
            line: parseInt(match[2], 10),
            column: match[3] !== undefined ? parseInt(match[3], 10) : 0
         };
      }
   }
   return { path: text, line: 0, column: 0 };
}

function repeatSpace(count)
{
   return new Array(count + 1).join(" ");
}


// The text of a buffer row, one string character per cell (two for a
// character outside the BMP), as xterm's translateToString() produces it.
// GHOSTTY_IMP: ghostty-web's own translateToString() yields nothing for an
// empty cell, which would shift every later offset, so empty cells are
// rendered as spaces here; the trailing half of a wide character has width 0
// and contributes nothing, as in xterm.
function lineToString(line, trimRight)
{
   var text = "";
   for (var i = 0; i < line.length; i++)
   {
      var cell = line.getCell(i);
      if (!cell || cell.getWidth() === 0)
         continue;
      text += cell.getChars() || " ";
   }
   return trimRight ? text.replace(/ +$/, "") : text;
}

// Collect the run of wrapped rows the given row belongs to, so a path that
// wraps across rows is seen whole. Rows other than the last keep their
// trailing whitespace so string offsets stay one-to-one with buffer cells.
function getWindowedLineStrings(terminal, lineIndex)
{
   var buffer = terminal.buffer.active;
   var lines = [];
   var startLine = lineIndex;
   var line = buffer.getLine(lineIndex);
   if (!line)
      return { lines: lines, startLine: startLine };

   var current = lineToString(line, true);
   var chars = 0;
   var previous;
   var text;

   // Spaces may be inside a quoted path, so collect all wrapped rows within
   // the size limit instead of treating whitespace as a token boundary.
   if (line.isWrapped)
   {
      while (chars < MAX_LINE_CHARS)
      {
         previous = buffer.getLine(startLine - 1);
         if (!previous)
            break;

         startLine--;
         text = lineToString(previous, false);
         chars += text.length;
         lines.push(text);
         if (!previous.isWrapped)
            break;
      }
      lines.reverse();
   }

   var next = buffer.getLine(lineIndex + 1);
   if (next && next.isWrapped)
      current = lineToString(line, false);
   lines.push(current);

   chars = 0;
   var nextIndex = lineIndex;
   while (chars < MAX_LINE_CHARS)
   {
      next = buffer.getLine(nextIndex + 1);
      if (!next || !next.isWrapped)
         break;

      nextIndex++;
      var following = buffer.getLine(nextIndex + 1);
      text = lineToString(next, !(following && following.isWrapped));
      chars += text.length;
      lines.push(text);
   }

   return { lines: lines, startLine: startLine };
}

// Map a string offset within the stitched line back to a buffer cell,
// walking cells from (lineIndex, cellIndex) and accounting for wide
// characters. Returns [-1, -1] if the buffer changed underneath us.
function mapStringIndex(terminal, lineIndex, cellIndex, stringIndex)
{
   var buffer = terminal.buffer.active;
   var start = cellIndex;

   while (stringIndex)
   {
      var line = buffer.getLine(lineIndex);
      if (!line)
         return [-1, -1];

      for (var i = start; i < line.length; i++)
      {
         var cell = line.getCell(i);
         if (!cell)
            return [-1, -1];

         var chars = cell.getChars();
         if (cell.getWidth())
         {
            stringIndex -= chars.length || 1;

            // a wide character that did not fit at the end of the row
            // leaves an empty cell behind and wraps to the next row
            if (i === line.length - 1 && chars === "")
            {
               var nextLine = buffer.getLine(lineIndex + 1);
               var first = nextLine && nextLine.isWrapped && nextLine.getCell(0);
               if (first && first.getWidth() === 2)
                  stringIndex += 1;
            }
         }
         if (stringIndex < 0)
            return [lineIndex, i];
      }

      lineIndex++;
      start = 0;
   }

   return [lineIndex, start];
}

// GHOSTTY_IMP: link ranges are 0-based, with an inclusive end column.
function computeRange(terminal, startLine, index, length)
{
   var start = mapStringIndex(terminal, startLine, 0, index);
   if (start[0] === -1)
      return null;

   var end = mapStringIndex(terminal, start[0], start[1], length);
   if (end[0] === -1)
      return null;

   // a token ending exactly at the row edge maps to column 0 of the next row
   if (end[1] === 0 && end[0] > start[0])
      end = [end[0] - 1, terminal.cols];

   return {
      start: { x: start[1], y: start[0] },
      end: { x: end[1] - 1, y: end[0] }
   };
}

root.RStudioFileLinks = {
   FileLinkProvider: FileLinkProvider,
   findCandidates: findCandidates
};

})(typeof window !== "undefined" ? window : globalThis);
