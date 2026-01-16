"""
Source Editor Widget

A text editor for R source files with:
- Syntax highlighting
- Line numbers
- Basic editing operations
- File save/load
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static, TextArea

if TYPE_CHECKING:
    from rstudio_tui.client import RSessionClient


class EditorHeader(Static):
    """Header showing file name and status."""

    DEFAULT_CSS = """
    EditorHeader {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, filename: str = "Untitled", modified: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.filename = filename
        self.modified = modified

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        indicator = "*" if self.modified else ""
        self.update(f"Source: {self.filename}{indicator}")

    def set_filename(self, filename: str) -> None:
        self.filename = filename
        self._update_display()

    def set_modified(self, modified: bool) -> None:
        self.modified = modified
        self._update_display()


class EditorStatusBar(Static):
    """Status bar showing cursor position and file info."""

    DEFAULT_CSS = """
    EditorStatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.line = 1
        self.column = 1
        self.encoding = "UTF-8"
        self.file_type = "R"

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        self.update(f"Ln {self.line}, Col {self.column} | {self.encoding} | {self.file_type}")

    def set_position(self, line: int, column: int) -> None:
        self.line = line
        self.column = column
        self._update_display()

    def set_file_type(self, file_type: str) -> None:
        self.file_type = file_type
        self._update_display()


class SourceTextArea(TextArea):
    """Extended TextArea with R syntax highlighting support."""

    DEFAULT_CSS = """
    SourceTextArea {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("ctrl+shift+s", "save_as", "Save As", show=False),
        Binding("ctrl+enter", "run_selection", "Run", show=True),
        Binding("ctrl+shift+enter", "run_all", "Run All", show=False),
        Binding("ctrl+/", "toggle_comment", "Comment", show=False),
    ]

    def __init__(
        self,
        on_save: Optional[callable] = None,
        on_run: Optional[callable] = None,
        **kwargs,
    ):
        super().__init__(language="r", theme="monokai", show_line_numbers=True, **kwargs)
        self._on_save = on_save
        self._on_run = on_run

    async def action_save(self) -> None:
        """Save the current file."""
        if self._on_save:
            self._on_save()

    async def action_save_as(self) -> None:
        """Save the current file with a new name."""
        # Would need a file dialog - for now just trigger save
        if self._on_save:
            self._on_save()

    async def action_run_selection(self) -> None:
        """Run the selected text or current line."""
        if self._on_run:
            text = self.selected_text or self._get_current_line()
            if text:
                self._on_run(text)

    async def action_run_all(self) -> None:
        """Run the entire document."""
        if self._on_run:
            self._on_run(self.text)

    async def action_toggle_comment(self) -> None:
        """Toggle comment on current line or selection."""
        # Get current selection or line
        if self.selection:
            start, end = self.selection
            lines = self.text.split("\n")
            start_line = self.text[:start].count("\n")
            end_line = self.text[:end].count("\n")

            for i in range(start_line, end_line + 1):
                if lines[i].lstrip().startswith("#"):
                    # Remove comment
                    lines[i] = lines[i].replace("# ", "", 1).replace("#", "", 1)
                else:
                    # Add comment
                    lines[i] = "# " + lines[i]

            self.text = "\n".join(lines)

    def _get_current_line(self) -> str:
        """Get the text of the current line."""
        if not self.text:
            return ""

        cursor_pos = self.cursor_location
        lines = self.text.split("\n")
        if 0 <= cursor_pos[0] < len(lines):
            return lines[cursor_pos[0]]
        return ""


class EditorWidget(Vertical):
    """
    Source code editor widget.

    Features:
    - Syntax highlighting for R code
    - Line numbers
    - File operations (open, save)
    - Code execution (run selection, run all)
    - Basic editing (cut, copy, paste, undo, redo)
    """

    DEFAULT_CSS = """
    EditorWidget {
        height: 100%;
        border: solid $secondary;
    }
    """

    def __init__(
        self,
        client: Optional[RSessionClient] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self._header: Optional[EditorHeader] = None
        self._editor: Optional[SourceTextArea] = None
        self._status: Optional[EditorStatusBar] = None
        self._file_path: Optional[Path] = None
        self._doc_id: Optional[str] = None
        self._modified: bool = False
        self._original_content: str = ""

    def compose(self) -> ComposeResult:
        yield EditorHeader()
        yield SourceTextArea(
            on_save=self._handle_save,
            on_run=self._handle_run,
        )
        yield EditorStatusBar()

    def on_mount(self) -> None:
        self._header = self.query_one(EditorHeader)
        self._editor = self.query_one(SourceTextArea)
        self._status = self.query_one(EditorStatusBar)

        # Track changes for modified indicator
        self._editor.watch(self._editor, "text", self._on_text_changed)

    def _on_text_changed(self) -> None:
        """Handle text changes."""
        if self._editor:
            is_modified = self._editor.text != self._original_content
            if is_modified != self._modified:
                self._modified = is_modified
                if self._header:
                    self._header.set_modified(self._modified)

    def _handle_save(self) -> None:
        """Handle save request."""
        if self._file_path:
            asyncio.create_task(self._save_file())

    async def _save_file(self) -> None:
        """Save the current file."""
        if not self._file_path or not self._editor:
            return

        try:
            if self.client and self._doc_id:
                # Save via rsession
                response = await self.client.save_document(
                    self._doc_id,
                    str(self._file_path),
                    self._editor.text,
                )
                if not response.success:
                    self.notify(f"Save failed: {response.error_message}", severity="error")
                    return
            else:
                # Save directly
                self._file_path.write_text(self._editor.text)

            self._original_content = self._editor.text
            self._modified = False
            if self._header:
                self._header.set_modified(False)
            self.notify(f"Saved: {self._file_path.name}")
        except Exception as e:
            self.notify(f"Save error: {e}", severity="error")

    def _handle_run(self, code: str) -> None:
        """Handle run code request."""
        if self.client:
            asyncio.create_task(self._run_code(code))
        else:
            self.notify("Not connected to R session", severity="warning")

    async def _run_code(self, code: str) -> None:
        """Run code in the console."""
        try:
            # Send each line as console input
            for line in code.strip().split("\n"):
                if line.strip():
                    await self.client.console_input(line)
        except Exception as e:
            self.notify(f"Run error: {e}", severity="error")

    async def open_file(self, path: Path) -> bool:
        """Open a file for editing."""
        try:
            if self.client:
                # Open via rsession
                response = await self.client.open_document(str(path))
                if response.success:
                    doc = response.result
                    self._doc_id = doc.get("id")
                    content = doc.get("contents", "")
                else:
                    # Fall back to direct read
                    content = path.read_text()
            else:
                content = path.read_text()

            self._file_path = path
            self._original_content = content

            if self._editor:
                self._editor.text = content

            if self._header:
                self._header.set_filename(path.name)
                self._header.set_modified(False)

            if self._status:
                # Detect file type from extension
                ext = path.suffix.lower()
                file_types = {
                    ".r": "R",
                    ".rmd": "R Markdown",
                    ".qmd": "Quarto",
                    ".py": "Python",
                    ".js": "JavaScript",
                    ".ts": "TypeScript",
                    ".json": "JSON",
                    ".yaml": "YAML",
                    ".yml": "YAML",
                    ".md": "Markdown",
                    ".txt": "Text",
                }
                self._status.set_file_type(file_types.get(ext, "Text"))

            self._modified = False
            return True
        except Exception as e:
            self.notify(f"Open error: {e}", severity="error")
            return False

    def new_file(self) -> None:
        """Create a new empty file."""
        self._file_path = None
        self._doc_id = None
        self._original_content = ""
        self._modified = False

        if self._editor:
            self._editor.text = ""

        if self._header:
            self._header.set_filename("Untitled")
            self._header.set_modified(False)

        if self._status:
            self._status.set_file_type("R")

    @property
    def file_path(self) -> Optional[Path]:
        """Get the current file path."""
        return self._file_path

    @property
    def is_modified(self) -> bool:
        """Check if the document has been modified."""
        return self._modified

    @property
    def content(self) -> str:
        """Get the current editor content."""
        return self._editor.text if self._editor else ""

    def focus_editor(self) -> None:
        """Focus the text editor."""
        if self._editor:
            self._editor.focus()
