# Updating ghostty-web for RStudio

RStudio's terminal is rendered by [ghostty-web](https://github.com/coder/ghostty-web):
Ghostty's terminal emulation library (libghostty-vt) compiled to WebAssembly, wrapped
in an xterm.js-compatible API. It is distributed via npm with the WebAssembly module
embedded in its UMD bundle.

Run the build-ghostty script from this folder to pull down the release and copy it
into the RStudio source tree. Then check the places marked `GHOSTTY_IMP` in
`XTermNative.java` and `file-links.js`, which rely on ghostty-web implementation
details rather than its documented API, and run the terminal file link tests:

    node --test src/gwt/test/terminal_file_links.test.cjs
