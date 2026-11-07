# Updating ghostty-web for RStudio

RStudio's terminal is rendered by [ghostty-web](https://github.com/coder/ghostty-web):
Ghostty's terminal emulation library (libghostty-vt) compiled to WebAssembly, wrapped
in an xterm.js-compatible API. It is distributed via npm with the WebAssembly module
embedded in its UMD bundle.

Run the build-ghostty script from this folder to pull down the release and copy it
into the RStudio source tree. Then check the places marked `GHOSTTY_IMP` in
`XTermNative.java`, `ghostty-theme.js`, `ghostty-a11y.js` and `file-links.js`,
which rely on ghostty-web implementation details rather than its documented API,
and run the terminal tests, which drive the real emulator:

    node --test src/gwt/test/terminal_*.test.cjs

Workarounds for ghostty-web 0.4.0 bugs, to drop once fixed upstream:

- An emulator created after a narrower one was freed shows leftover memory in
  its blank cells (`XTermNative.clearNewEmulator`).
- The emulator rejects OSC 4/10/11 color changes and ignores a theme set after
  `open()`, so theme changes are applied while rendering (`ghostty-theme.js`).
- A theme color of `#000000` is read as "use the built-in default"
  (`forEmulator` in `ghostty-theme.js`).
- A BEL that terminates an OSC sequence is reported as a bell
  (`XTermNative.writeTracked`).
