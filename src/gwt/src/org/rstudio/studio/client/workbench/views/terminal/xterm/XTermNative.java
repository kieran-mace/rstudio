/*
 * XTermNative.java
 *
 * Copyright (C) 2022 by Posit Software, PBC
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

package org.rstudio.studio.client.workbench.views.terminal.xterm;

import org.rstudio.core.client.CommandWithArg;

import com.google.gwt.core.client.JavaScriptObject;
import com.google.gwt.core.client.JsArrayString;
import com.google.gwt.dom.client.Element;
import com.google.gwt.user.client.Command;

/**
 * <code>JavaScriptObject</code> wrapper for the terminal emulator: ghostty-web,
 * which is libghostty-vt (Ghostty's terminal emulation core) compiled to
 * WebAssembly, behind an xterm.js-compatible API.
 *
 * Reliance on ghostty-web implementation details (rather than its documented,
 * xterm.js-compatible API: https://github.com/coder/ghostty-web) is marked
 * with GHOSTTY_IMP. Be careful of these when updating to a newer ghostty-web
 * build (see src/gwt/tools/build-ghostty).
 */
public class XTermNative extends JavaScriptObject
{
   // Required by JavaScriptObject subclasses
   protected XTermNative()
   {
   }

   /**
    * Load the terminal emulator's WebAssembly module. Must complete before
    * any terminal is created.
    * @param onLoaded called once the module is ready
    * @param onError called with a message if it could not be loaded
    */
   public static native void initialize(Command onLoaded, CommandWithArg<String> onError) /*-{
      var done = $entry(function() {
         onLoaded.@com.google.gwt.user.client.Command::execute()();
      });
      var fail = $entry(function(error) {
         onError.@org.rstudio.core.client.CommandWithArg::execute(Ljava/lang/Object;)("" + error);
      });

      try {
         $wnd.GhosttyWeb.init().then(done, fail);
      } catch (error) {
         fail(error);
      }
   }-*/;

   /**
    * Remove event handlers and detach from parent node.
    */
   public final native void dispose() /*-{
      this.dispose();
   }-*/;

   /**
    * Fit the terminal to available space.
    */
   public final native void fit() /*-{
      this.rstudioFitAddon_.fit();
   }-*/;

   /**
    * Write a line of output to the terminal, appending CR/LF.
    * @param data String to write
    */
   public final native void writeln(String data) /*-{
      @org.rstudio.studio.client.workbench.views.terminal.xterm.XTermNative::writeTracked(*)(this, data + "\r\n");
   }-*/;

   /**
    * Write text to the terminal.
    * @param data String to write
    */
   public final native void write(String data) /*-{
      @org.rstudio.studio.client.workbench.views.terminal.xterm.XTermNative::writeTracked(*)(this, data);
   }-*/;

   /**
    * Write output, noting whether it rings the bell. ghostty-web reports a
    * bell for any BEL in written data, including the one that terminates an
    * OSC sequence (such as the title most shells set at every prompt), so the
    * bell handler consults this to ignore those.
    */
   private static native void writeTracked(XTermNative term, String data) /*-{
      // drop string sequences (OSC, DCS, SOS, PM, APC) terminated by BEL or ST
      var visible = data.replace(/\x1b[\]PX^_][^\x07\x1b]*(?:\x07|\x1b\\)/g, "");
      term.rstudioWriteRingsBell_ = visible.indexOf("\x07") !== -1;
      term.rstudioWriting_ = true;
      try {
         term.write(data);
      } finally {
         term.rstudioWriting_ = false;
      }
   }-*/;

   /**
    * Compute and return available dimensions for terminal.
    * @return Visible number of columns and rows; zero if they cannot be
    * measured yet
    */
   public final native XTermDimensions proposeGeometry() /*-{
      return this.rstudioFitAddon_.proposeDimensions() || { cols: 0, rows: 0 };
   }-*/;

   public final native void focus() /*-{
      this.focus();
   }-*/;

   public final native void blur() /*-{
      this.blur();
   }-*/;

   public final native void scrollLines(int lineCount) /*-{
      this.scrollLines(lineCount);
   }-*/;

   public final native void scrollToBottom() /*-{
      this.scrollToBottom();
   }-*/;

   public final native void reset() /*-{
      this.reset();

      // reset() rebuilds the emulator from the options it was created with
      if (this.rstudioTheme_)
         @org.rstudio.studio.client.workbench.views.terminal.xterm.XTermNative::applyTheme(*)(this, this.rstudioTheme_);
   }-*/;

   public final native void clear() /*-{
      this.clear();
   }-*/;

   public final native void addClass(String classStr) /*-{
      this.element.classList.add(classStr);
   }-*/;

   public final native void removeClass(String classStr) /*-{
      this.element.classList.remove(classStr);
   }-*/;

   /**
    * @return cursor column, 0-based
    */
   public final native int cursorX() /*-{
      return this.buffer.active.cursorX;
   }-*/;

   /**
    * @return cursor row within the visible screen, 0-based
    */
   public final native int cursorY() /*-{
      return this.buffer.active.cursorY;
   }-*/;

   public final native boolean altBufferActive() /*-{
      return this.buffer.active.type === "alternate";
   }-*/;

   public final native void showPrimaryBuffer() /*-{
      this.write("\x1b[?1047l"); // show primary buffer
      this.write("\x1b[m"); // reset all visual attributes
      this.write("\x1b[?9l"); // reset mouse mode
   }-*/;

   public final native void showAltBuffer() /*-{
      this.write("\x1b[?1047h"); // show alt buffer
   }-*/;

   /**
    * @return the text of the cursor's row, one character per cell (blank
    * cells as spaces), or null if it is unavailable
    */
   public final native String currentLine() /*-{
      // buffer rows are numbered from the top of the scrollback, and the
      // screen is the last `rows` of them
      var buffer = this.buffer.active;
      var lineBuf = buffer.getLine(buffer.length - this.rows + buffer.cursorY);
      if (!lineBuf) // resize may be in progress
         return null;

      // GHOSTTY_IMP: translateToString() drops blank cells rather than
      // rendering them as spaces, so build the text cell by cell; the
      // trailing half of a wide character has width 0
      var text = "";
      for (var i = 0; i < lineBuf.length; i++) {
         var cell = lineBuf.getCell(i);
         if (cell && cell.getWidth() !== 0)
            text += cell.getChars() || " ";
      }
      return text;
   }-*/;

   /**
    * Install a handler for user input (typing). Only one handler at a
    * time may be installed. Previous handler will be overwritten.
    * @param command handler for data typed by the user
    */
   public final native void onTerminalData(CommandWithArg<String> command) /*-{
      if (this.dataHandler)
         this.dataHandler.dispose();
      this.dataHandler = this.onData(
         $entry(function(data) {
            command.@org.rstudio.core.client.CommandWithArg::execute(Ljava/lang/Object;)(data);
         }));
   }-*/;

   /**
    * Install a handler for title events (via escape sequence).
    * @param command handler for title text
    */
   public final native void onTitleData(CommandWithArg<String> command) /*-{
      if (this.handleTitle)
         this.handleTitle.dispose();
      this.handleTitle = this.onTitleChange(
         $entry(function(title) {
            command.@org.rstudio.core.client.CommandWithArg::execute(Ljava/lang/Object;)(title);
         }));
   }-*/;

   /**
    * Install a handler for bell events (BEL character received).
    * @param command handler to execute when bell sounds
    */
   public final native void onBellEvent(Command command) /*-{
      var term = this;
      if (this.bellHandler)
         this.bellHandler.dispose();
      this.bellHandler = this.onBell(
         $entry(function() {
            // a BEL that only terminated a string sequence (see writeTracked)
            if (term.rstudioWriting_ && !term.rstudioWriteRingsBell_)
               return;
            command.@com.google.gwt.user.client.Command::execute()();
         }));
   }-*/;

   /**
    * Change the terminal's colors, including for output already shown.
    */
   public final native void updateTheme(XTermTheme theme) /*-{
      this.rstudioTheme_ = theme;
      @org.rstudio.studio.client.workbench.views.terminal.xterm.XTermNative::applyTheme(*)(this, theme);
   }-*/;

   /**
    * ghostty-web takes its colors from the options it was created with, and
    * ignores (with a warning) a theme set later. Instead, give the renderer
    * the new theme and give the emulator the new palette and default colors
    * through the escape sequences programs use to change them (OSC 4, 10, 11
    * and 12), so cells already on screen pick them up as well.
    */
   private static native void applyTheme(XTermNative term, XTermTheme theme) /*-{
      // GHOSTTY_IMP: the canvas renderer and the WebAssembly emulator
      if (!term.renderer || !term.wasmTerm)
         return;

      term.renderer.setTheme(theme);

      var toHex = function(color) {
         if (!color)
            return null;
         if (/^#[0-9a-fA-F]{6}$/.test(color))
            return color;
         if (/^#[0-9a-fA-F]{3}$/.test(color))
            return "#" + color.charAt(1) + color.charAt(1) + color.charAt(2) +
                         color.charAt(2) + color.charAt(3) + color.charAt(3);
         var rgb = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/.exec(color);
         if (!rgb)
            return null;
         var hex = "#";
         for (var i = 1; i <= 3; i++) {
            var part = Math.min(255, parseInt(rgb[i], 10)).toString(16);
            hex += part.length === 1 ? "0" + part : part;
         }
         return hex;
      };

      var sequences = "";
      var osc = function(code, color) {
         var hex = toHex(color);
         if (hex)
            sequences += "\x1b]" + code + ";" + hex + "\x1b\\";
      };

      var palette = [
         theme.black, theme.red, theme.green, theme.yellow,
         theme.blue, theme.magenta, theme.cyan, theme.white,
         theme.brightBlack, theme.brightRed, theme.brightGreen, theme.brightYellow,
         theme.brightBlue, theme.brightMagenta, theme.brightCyan, theme.brightWhite
      ];
      for (var i = 0; i < palette.length; i++)
         osc("4;" + i, palette[i]);
      osc("10", theme.foreground);
      osc("11", theme.background);
      osc("12", theme.cursor);

      // straight to the emulator: these are not output, so must not move the
      // viewport, ring the bell or set the title as term.write() might
      if (sequences)
         term.wasmTerm.write(sequences);

      term.renderer.render(term.wasmTerm, true, term.viewportY, term);
   }-*/;

   public final native void updateBooleanOption(String option, boolean value) /*-{
      this.options[option] = value;
   }-*/;

   public final native void updateStringOption(String option, String value) /*-{
      this.options[option] = value;
   }-*/;

   public final native void updateDoubleOption(String option, double value) /*-{
      this.options[option] = value;
   }-*/;

   /**
    * Repaint the whole terminal.
    */
   public final native void refresh() /*-{
      // GHOSTTY_IMP: the canvas renderer and the WebAssembly emulator; the
      // render loop only repaints rows the emulator reports as changed
      if (this.renderer && this.wasmTerm)
         this.renderer.render(this.wasmTerm, true, this.viewportY, this);
   }-*/;

   public final native void setTabMovesFocus(boolean movesFocus) /*-{
      this.tabMovesFocus = movesFocus;
   }-*/;

   /**
    * Register the link provider that makes file paths in terminal output
    * clickable (with the platform's open-link modifier held). Candidate
    * validation, opening, and the hover hint are delegated to the widget.
    * @param widget owning widget, called back on the UI thread
    * @param isMac use Cmd rather than Ctrl as the activation modifier
    */
   public final native void registerFileLinkProvider(XTermWidget widget, boolean isMac) /*-{
      if (this.rstudioFileLinks_ || !$wnd.RStudioFileLinks)
         return;

      var term = this;

      // GHOSTTY_IMP: the link detector caches the links found on each row
      // until the terminal is next written to; drop them so rows are asked
      // about again, then look again at what is under the pointer.
      var rescan = function() {
         if (!term.linkDetector)
            return;
         term.linkDetector.invalidateCache();
         if (term.rstudioLastMouseMove_ && term.processMouseMove)
            term.processMouseMove(term.rstudioLastMouseMove_);
      };
      this.rstudioFileLinkRefresh_ = function() {
         if (term.linkDetector)
            term.linkDetector.invalidateCache();
      };

      this.element.addEventListener("mousemove", function(event) {
         term.rstudioLastMouseMove_ = event;
      }, true);
      this.element.addEventListener("mouseleave", function() {
         term.rstudioLastMouseMove_ = null;
      });

      var host = {
         isMac: isMac,
         resolve: $entry(function(candidates, callback) {
            widget.@org.rstudio.studio.client.workbench.views.terminal.xterm.XTermWidget::resolveFileLinksNative(Lcom/google/gwt/core/client/JsArrayString;Lcom/google/gwt/core/client/JavaScriptObject;)(candidates, callback);
         }),
         open: $entry(function(path, line, column) {
            widget.@org.rstudio.studio.client.workbench.views.terminal.xterm.XTermWidget::openFileLink(Ljava/lang/String;II)(path, line, column);
         }),
         hover: $entry(function(path) {
            widget.@org.rstudio.studio.client.workbench.views.terminal.xterm.XTermWidget::showFileLinkHint(Ljava/lang/String;)(path);
         }),
         leave: $entry(function() {
            widget.@org.rstudio.studio.client.workbench.views.terminal.xterm.XTermWidget::hideFileLinkHint()();
         }),
         modifierChanged: function() {
            // deferred: the change may be reported by a mouse event that is
            // still on its way to the terminal's own (throttled) handler
            $wnd.setTimeout(rescan, 0);
         }
      };

      try {
         var provider = new $wnd.RStudioFileLinks.FileLinkProvider(this, host);
         this.rstudioFileLinks_ = provider;
         this.registerLinkProvider(provider);
      } catch (error) {
         console.error("Error registering file link provider: " + error);
      }
   }-*/;

   /**
    * Forget cached file link resolutions; used when the terminal's working
    * directory changes, since relative paths then resolve differently.
    */
   public final native void clearFileLinkCache() /*-{
      if (this.rstudioFileLinks_)
      {
         this.rstudioFileLinks_.clearCache();
         this.rstudioFileLinkRefresh_();
      }
   }-*/;

   /**
    * Release any link the file link provider is still showing, and stop it
    * following the open-link modifier; used when the terminal is torn down,
    * since a detached element never reports the mouse leaving.
    */
   public final native void disposeFileLinkProvider() /*-{
      if (this.rstudioFileLinks_)
         this.rstudioFileLinks_.dispose();
   }-*/;

   /**
    * Invoke a JavaScript callback with an array of strings.
    */
   public static native void invokeCallback(JavaScriptObject callback, JsArrayString result) /*-{
      callback(result);
   }-*/;

   /**
    * Factory to create a native Javascript terminal object. The emulator must
    * have been initialized (see initialize()).
    *
    * @param container HTML element to attach to
    * @param options terminal settings
    *
    * @return Native Javascript Terminal object wrapped in a <code>JavaScriptObject</code>.
    */
   public static native XTermNative createTerminal(Element container,
                                                   XTermOptions options,
                                                   boolean clickableLinks,
                                                   boolean tabMovesFocus) /*-{
      try {
         var ghostty = $wnd.GhosttyWeb;
         var nativeTerm_ = new ghostty.Terminal(options);
         nativeTerm_.rstudioTheme_ = options.theme;
         try {
            nativeTerm_.rstudioFitAddon_ = new ghostty.FitAddon();
            nativeTerm_.loadAddon(nativeTerm_.rstudioFitAddon_);
         } catch (error) {
            console.error("Error loading FitAddon: " + error);
         }

         nativeTerm_.open(container);
         nativeTerm_.tabMovesFocus = tabMovesFocus;

         // The desktop app recognizes the terminal by this class on the
         // focused element (see src/node/desktop/src/main/context-menu.ts).
         nativeTerm_.textarea.classList.add("xterm-helper-textarea");

         // Select All in the desktop right-click menu sends this event to the
         // focused helper textarea: the browser's own select-all would select
         // only the textarea's text, not the terminal's buffer.
         nativeTerm_.textarea.addEventListener("rstudio-terminal-select-all", function() {
            nativeTerm_.selectAll();
         });

         // Web links. GHOSTTY_IMP: the terminal's link detector comes with
         // providers for OSC 8 hyperlinks and for URLs in the text, which open
         // links with window.open(). Take them over so that RStudio Desktop
         // opens links in the system browser, and drop them when links are
         // turned off.
         var openUrl = function(uri) {
            if ($wnd.desktop && $wnd.desktop.browseUrl) {
               $wnd.desktop.browseUrl(uri);
            } else {
               $wnd.open(uri, "_blank", "noopener,noreferrer");
            }
         };
         var wrapWebLinkProvider = function(inner) {
            return {
               provideLinks: function(row, callback) {
                  inner.provideLinks(row, function(links) {
                     if (links) {
                        for (var i = 0; i < links.length; i++) {
                           (function(link) {
                              link.activate = function(event) {
                                 // as xterm's web links addon did, a plain
                                 // click opens the link; but not one that
                                 // finishes selecting text
                                 if (event.button === 0 && !nativeTerm_.hasSelection())
                                    openUrl(link.text);
                              };
                           })(links[i]);
                        }
                     }
                     callback(links);
                  });
               },
               dispose: function() {
                  if (inner.dispose)
                     inner.dispose();
               }
            };
         };
         var detector = nativeTerm_.linkDetector;
         if (detector && detector.providers) {
            var builtIn = detector.providers;
            detector.providers = [];
            if (clickableLinks) {
               for (var p = 0; p < builtIn.length; p++)
                  detector.registerProvider(wrapWebLinkProvider(builtIn[p]));
            }
         }

         // Copy through the browser's copy command, which works over plain
         // http (unlike the async clipboard API), which is how RStudio Server
         // is often reached. ghostty-web has no copy handler of its own, so
         // supply the selection to every copy aimed at the terminal; that
         // also covers Cmd+C, and Copy in the desktop right-click menu.
         container.addEventListener("copy", function(event) {
            if (!nativeTerm_.hasSelection() || !event.clipboardData)
               return;
            event.clipboardData.setData("text/plain", nativeTerm_.getSelection());
            event.preventDefault();
         });

         var copySelection = function() {
            var copied = false;
            try {
               copied = $doc.execCommand("copy");
            } catch (error) {
               console.warn("Terminal copy failed: " + error);
            }

            var clipboard = $wnd.navigator.clipboard;
            if (!copied && clipboard && clipboard.writeText) {
               clipboard.writeText(nativeTerm_.getSelection())["catch"](function(error) {
                  console.warn("Terminal copy failed: " + error);
               });
            }
         };

         var pasteFromClipboard = function() {
            if ($wnd.desktop && $wnd.desktop.getClipboardText) {
               $wnd.desktop.getClipboardText(function(text) {
                  if (text)
                     nativeTerm_.paste(text);
               });
               return;
            }

            var clipboard = $wnd.navigator.clipboard;
            if (clipboard && clipboard.readText) {
               clipboard.readText().then(function(text) {
                  if (text)
                     nativeTerm_.paste(text);
               })["catch"](function(error) {
                  console.warn("Terminal paste failed: " + error);
               });
            }
         };

         // Chromium's plain-text paste (Ctrl+Shift+V on Windows and Linux)
         // dispatches a paste event that the terminal already handles;
         // remember when one arrives so the fallback below doesn't paste a
         // second time.
         var pasteEventSeen = false;
         container.addEventListener("paste", function() {
            pasteEventSeen = true;
         }, true);

         // With "Tab moves focus" on, let Tab leave the terminal. The
         // terminal's key handler would either send it to the shell or, if
         // told the key was handled, cancel the browser's focus change, so
         // keep the key from reaching it at all.
         container.addEventListener("keydown", function(event) {
            if (event.keyCode === 9 && nativeTerm_.tabMovesFocus)
               event.stopImmediatePropagation();
         }, true);

         // Unlike xterm.js, ghostty-web's custom key handler returns true for
         // a key it has handled (the terminal then cancels the key's default
         // action and sends nothing), and false to let the terminal process it.
         nativeTerm_.attachCustomKeyEventHandler(function(event) {
            if (event.type !== "keydown" || event.altKey || event.metaKey)
               return false;

            // Ctrl+Insert / Shift+Insert copy and paste, as in xterm.js
            if (event.keyCode === 45) {
               if (event.ctrlKey && !event.shiftKey) {
                  if (nativeTerm_.hasSelection())
                     copySelection();
                  return true;
               }
               if (event.shiftKey && !event.ctrlKey) {
                  pasteFromClipboard();
                  return true;
               }
               return false;
            }

            // Ctrl+Shift+C / Ctrl+Shift+V copy and paste, as in most terminal
            // emulators (#1687). Neither sends anything to the shell in other
            // terminals, so no key sequence is lost to this.
            if (!(event.ctrlKey && event.shiftKey))
               return false;

            if (event.keyCode === 67) {
               if (nativeTerm_.hasSelection())
                  copySelection();

               // Consume the key even with nothing selected: left to the
               // browser it opens the developer tools, and on Windows and
               // Linux desktop it would fall through to the Comment/Uncomment
               // menu accelerator bound to the same keys.
               return true;
            }

            if (event.keyCode === 86) {
               // Let the browser's own paste run first (the terminal leaves
               // Ctrl+V keys to the browser), and read the clipboard ourselves
               // only when it produced no paste event (Firefox has no
               // plain-text paste key for text areas; macOS uses Cmd).
               pasteEventSeen = false;
               $wnd.setTimeout(function() {
                  if (!pasteEventSeen)
                     pasteFromClipboard();
               }, 0);
            }

            return false;
         });

         nativeTerm_.focus();
         return nativeTerm_;
      } catch (error) {
         console.error("Error creating terminal: " + error);
      }
      return undefined;
   }-*/;
}
