/*
 * ghostty-theme.js
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

// Theme changes for ghostty-web terminals.
//
// ghostty-web (0.4.0, pinned in src/gwt/tools/build-ghostty) bakes a terminal's
// default colors and 16-color palette into its WebAssembly emulator when the
// terminal is created, and reports every cell with its color already resolved
// to RGB. A theme set afterwards is ignored, and the emulator rejects the
// escape sequences (OSC 4, 10 and 11) that would change those colors.
//
// So the emulator keeps the theme it was created with, and the terminal's
// renderer translates as it draws: each cell whose color is one of the
// creation theme's palette or default colors is drawn in the matching color
// of the current theme. 256-color and true-color output is left alone, as a
// terminal theme only defines the first 16 colors. The cells the renderer is
// given are fresh copies (GHOSTTY_IMP: CanvasRenderer.renderLine, fed by
// GhosttyTerminal.getLine and getScrollbackLine), so they are translated in
// place.

(function(root) {
"use strict";

var PALETTE = [
   "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
   "brightBlack", "brightRed", "brightGreen", "brightYellow",
   "brightBlue", "brightMagenta", "brightCyan", "brightWhite"
];

// Parse a CSS color as found in a theme (#rgb, #rrggbb, rgb() or rgba()) to
// 0xRRGGBB, or null.
function parseColor(color)
{
   if (typeof color !== "string")
      return null;

   color = color.trim();
   var match = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color);
   if (match)
   {
      var hex = match[1];
      if (hex.length === 3)
         hex = hex.charAt(0) + hex.charAt(0) + hex.charAt(1) + hex.charAt(1) + hex.charAt(2) + hex.charAt(2);
      return parseInt(hex, 16);
   }

   match = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(color);
   if (match)
   {
      var r = Math.min(255, parseInt(match[1], 10));
      var g = Math.min(255, parseInt(match[2], 10));
      var b = Math.min(255, parseInt(match[3], 10));
      return (r << 16) | (g << 8) | b;
   }

   return null;
}

function toHex(value)
{
   var hex = value.toString(16);
   while (hex.length < 6)
      hex = "0" + hex;
   return "#" + hex;
}

// The theme to create the emulator with. GHOSTTY_IMP: the emulator takes a
// color of 0 (black) to mean "use the built-in default", and only parses the
// #rrggbb and rgb() forms; give it a black it will use (#000001, which no one
// can tell from #000000), and every other color as #rrggbb.
function forEmulator(theme)
{
   if (!theme)
      return theme;

   var result = {};
   for (var key in theme)
   {
      if (Object.prototype.hasOwnProperty.call(theme, key))
         result[key] = theme[key];
   }

   var keys = PALETTE.concat(["foreground", "background", "cursor"]);
   for (var i = 0; i < keys.length; i++)
   {
      var value = parseColor(theme[keys[i]]);
      if (value !== null)
         result[keys[i]] = toHex(value === 0 ? 1 : value);
   }
   return result;
}

// The translation from the colors of `base` (a theme as given to
// forEmulator()) to those of `theme`, separately for foregrounds and
// backgrounds: when a default color is also a palette color, cells in the
// default foreground follow the new foreground, and cells on the default
// background follow the new background. Returns null when nothing changes.
function buildColorMaps(base, theme)
{
   // both sides as the emulator would have them, so that the creation theme
   // maps to itself
   base = forEmulator(base) || {};
   theme = forEmulator(theme) || {};

   var fg = {}, bg = {};
   var changed = false;

   function add(maps, from, to)
   {
      var source = parseColor(base[from]);
      var target = parseColor(theme[to]);
      if (source === null || target === null)
         return;
      for (var i = 0; i < maps.length; i++)
         maps[i][source] = target;
      if (source !== target)
         changed = true;
   }

   for (var i = 0; i < PALETTE.length; i++)
      add([fg, bg], PALETTE[i], PALETTE[i]);
   add([fg], "foreground", "foreground");
   add([bg], "background", "background");

   return changed ? { fg: fg, bg: bg } : null;
}

// Translate the colors of a row of ghostty cells in place.
function remapCells(cells, maps)
{
   for (var i = 0; i < cells.length; i++)
   {
      var cell = cells[i];

      var key = (cell.fg_r << 16) | (cell.fg_g << 8) | cell.fg_b;
      var value = maps.fg[key];
      if (value !== undefined)
      {
         cell.fg_r = (value >> 16) & 255;
         cell.fg_g = (value >> 8) & 255;
         cell.fg_b = value & 255;
      }

      key = (cell.bg_r << 16) | (cell.bg_g << 8) | cell.bg_b;
      value = maps.bg[key];
      if (value !== undefined)
      {
         cell.bg_r = (value >> 16) & 255;
         cell.bg_g = (value >> 8) & 255;
         cell.bg_b = value & 255;
      }
   }
}

// Follows theme changes for one terminal. `baseTheme` is the theme its
// emulator was created with (before forEmulator()); the emulator is rebuilt
// from the same options on reset(), so it stays the base for good.
function ThemeTracker(renderer, baseTheme)
{
   var self = this;
   this._renderer = renderer;
   this._base = baseTheme;
   this._maps = null;

   var renderLine = renderer.renderLine;
   renderer.renderLine = function(cells, row, cols) {
      if (self._maps && cells)
         remapCells(cells, self._maps);
      return renderLine.apply(this, arguments);
   };
}

ThemeTracker.prototype.setTheme = function(theme)
{
   this._maps = buildColorMaps(this._base, theme);
   this._renderer.setTheme(theme);
};

root.RStudioTerminalTheme = {
   ThemeTracker: ThemeTracker,
   forEmulator: forEmulator,
   buildColorMaps: buildColorMaps,
   remapCells: remapCells,
   parseColor: parseColor
};

})(typeof window !== "undefined" ? window : globalThis);
