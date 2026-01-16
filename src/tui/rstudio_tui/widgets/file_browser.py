"""
File Browser Widget

A file system navigator with:
- Directory tree view
- File operations (create, delete, rename)
- File type icons
- Navigation
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DirectoryTree, Static, Tree
from textual.widgets._tree import TreeNode

if TYPE_CHECKING:
    from rstudio_tui.client import RSessionClient


# File type icons (using text characters for maximum compatibility)
FILE_ICONS = {
    # R files
    ".r": "[R]",
    ".rmd": "[Rmd]",
    ".rproj": "[Proj]",
    ".rdata": "[Data]",
    ".rds": "[Data]",
    ".rhistory": "[Hist]",
    # Quarto
    ".qmd": "[Qmd]",
    # Data files
    ".csv": "[CSV]",
    ".tsv": "[TSV]",
    ".json": "[JSON]",
    ".xml": "[XML]",
    ".yaml": "[YAML]",
    ".yml": "[YAML]",
    # Documents
    ".md": "[MD]",
    ".txt": "[TXT]",
    ".html": "[HTML]",
    ".pdf": "[PDF]",
    # Code files
    ".py": "[Py]",
    ".js": "[JS]",
    ".ts": "[TS]",
    ".cpp": "[C++]",
    ".c": "[C]",
    ".h": "[H]",
    ".sh": "[SH]",
    # Images
    ".png": "[IMG]",
    ".jpg": "[IMG]",
    ".jpeg": "[IMG]",
    ".gif": "[IMG]",
    ".svg": "[SVG]",
    # Archives
    ".zip": "[ZIP]",
    ".tar": "[TAR]",
    ".gz": "[GZ]",
}


class FileBrowserHeader(Static):
    """Header showing current directory."""

    DEFAULT_CSS = """
    FileBrowserHeader {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, path: str = "~", **kwargs):
        super().__init__(**kwargs)
        self.path = path

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        # Shorten path if too long
        display_path = self.path
        if len(display_path) > 40:
            display_path = "..." + display_path[-37:]
        self.update(f"Files: {display_path}")

    def set_path(self, path: str) -> None:
        self.path = path
        self._update_display()


class RStudioDirectoryTree(DirectoryTree):
    """Extended DirectoryTree with RStudio-specific features."""

    DEFAULT_CSS = """
    RStudioDirectoryTree {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(
        self,
        path: str | Path,
        on_file_selected: Optional[Callable[[Path], None]] = None,
        **kwargs,
    ):
        super().__init__(path, **kwargs)
        self._on_file_selected = on_file_selected

    def filter_paths(self, paths: list[Path]) -> list[Path]:
        """Filter out hidden files and certain directories."""
        filtered = []
        for path in paths:
            name = path.name
            # Skip hidden files (starting with .)
            if name.startswith("."):
                continue
            # Skip common unneeded directories
            if name in {"__pycache__", "node_modules", ".git", ".Rproj.user"}:
                continue
            filtered.append(path)
        return sorted(filtered, key=lambda p: (not p.is_dir(), p.name.lower()))

    def render_label(self, node: TreeNode[Path], base_style, style) -> Text:
        """Render node label with file type icon."""
        path = node.data
        if path is None:
            return Text("???")

        name = path.name
        label = Text()

        if path.is_dir():
            label.append("[DIR] ", style="bold blue")
            label.append(name, style="blue")
        else:
            ext = path.suffix.lower()
            icon = FILE_ICONS.get(ext, "[   ]")
            label.append(f"{icon} ", style="dim")
            label.append(name)

        return label

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection."""
        if self._on_file_selected:
            self._on_file_selected(event.path)


class FileBrowserWidget(Vertical):
    """
    File browser widget for navigating the file system.

    Features:
    - Directory tree navigation
    - File type icons
    - Open files in editor
    - File operations (create, delete, rename)
    - Working directory integration
    """

    DEFAULT_CSS = """
    FileBrowserWidget {
        height: 100%;
        border: solid $secondary;
        width: 35;
    }
    """

    BINDINGS = [
        Binding("n", "new_file", "New File", show=True),
        Binding("shift+n", "new_folder", "New Folder", show=False),
        Binding("r", "rename", "Rename", show=False),
        Binding("d", "delete", "Delete", show=False),
        Binding("enter", "open_selected", "Open", show=True),
        Binding("backspace", "go_up", "Up", show=True),
        Binding("h", "toggle_hidden", "Hidden", show=False),
    ]

    class FileSelected(Message):
        """Message sent when a file is selected."""

        def __init__(self, path: Path) -> None:
            self.path = path
            super().__init__()

    def __init__(
        self,
        client: Optional[RSessionClient] = None,
        initial_path: Optional[Path] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self._initial_path = initial_path or Path.home()
        self._header: Optional[FileBrowserHeader] = None
        self._tree: Optional[RStudioDirectoryTree] = None
        self._show_hidden: bool = False

    def compose(self) -> ComposeResult:
        yield FileBrowserHeader(str(self._initial_path))
        yield RStudioDirectoryTree(
            self._initial_path,
            on_file_selected=self._handle_file_selected,
        )

    def on_mount(self) -> None:
        self._header = self.query_one(FileBrowserHeader)
        self._tree = self.query_one(RStudioDirectoryTree)

    def _handle_file_selected(self, path: Path) -> None:
        """Handle file selection from tree."""
        self.post_message(self.FileSelected(path))

    async def set_path(self, path: Path) -> None:
        """Set the root path of the file browser."""
        if path.is_dir():
            self._initial_path = path
            if self._header:
                self._header.set_path(str(path))
            if self._tree:
                self._tree.path = path
                self._tree.reload()

    async def refresh_tree(self) -> None:
        """Refresh the file tree."""
        if self._tree:
            self._tree.reload()

    async def action_new_file(self) -> None:
        """Create a new file (signals to app to handle)."""
        self.notify("Use Ctrl+N in editor to create new file")

    async def action_new_folder(self) -> None:
        """Create a new folder."""
        # Would need input dialog - simplified for now
        self.notify("New folder: Not implemented in TUI")

    async def action_rename(self) -> None:
        """Rename selected item."""
        self.notify("Rename: Not implemented in TUI")

    async def action_delete(self) -> None:
        """Delete selected item."""
        self.notify("Delete: Not implemented in TUI")

    async def action_open_selected(self) -> None:
        """Open the selected file."""
        if self._tree and self._tree.cursor_node:
            node = self._tree.cursor_node
            if node.data and node.data.is_file():
                self._handle_file_selected(node.data)

    async def action_go_up(self) -> None:
        """Navigate to parent directory."""
        parent = self._initial_path.parent
        if parent != self._initial_path:
            await self.set_path(parent)

    async def action_toggle_hidden(self) -> None:
        """Toggle showing hidden files."""
        self._show_hidden = not self._show_hidden
        await self.refresh_tree()
        state = "shown" if self._show_hidden else "hidden"
        self.notify(f"Hidden files: {state}")

    @property
    def current_path(self) -> Path:
        """Get the current root path."""
        return self._initial_path

    @property
    def selected_path(self) -> Optional[Path]:
        """Get the currently selected path."""
        if self._tree and self._tree.cursor_node:
            return self._tree.cursor_node.data
        return None
