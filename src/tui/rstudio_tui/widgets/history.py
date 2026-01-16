"""
History Widget

Displays R command history with:
- Searchable list
- Timestamp display
- Re-run commands
- Copy to clipboard
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable, List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, ListItem, ListView, Static

if TYPE_CHECKING:
    from rstudio_tui.client import RSessionClient


@dataclass
class HistoryEntry:
    """Represents a command history entry."""

    index: int
    command: str
    timestamp: Optional[datetime] = None


class HistoryHeader(Static):
    """Header for the history panel."""

    DEFAULT_CSS = """
    HistoryHeader {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self, count: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.count = count

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        self.update(f"History ({self.count} commands)")

    def set_count(self, count: int) -> None:
        self.count = count
        self._update_display()


class HistorySearchInput(Input):
    """Search input for filtering history."""

    DEFAULT_CSS = """
    HistorySearchInput {
        dock: top;
        height: 1;
        margin: 0;
        border: none;
        background: $surface;
    }
    """

    def __init__(self, on_filter: Optional[Callable[[str], None]] = None, **kwargs):
        super().__init__(placeholder="Filter history...", **kwargs)
        self._on_filter = on_filter

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for filtering."""
        if self._on_filter:
            self._on_filter(self.value)


class HistoryItem(ListItem):
    """A single history item in the list."""

    DEFAULT_CSS = """
    HistoryItem {
        height: auto;
        padding: 0 1;
    }

    HistoryItem:hover {
        background: $accent;
    }
    """

    def __init__(self, entry: HistoryEntry, **kwargs):
        super().__init__(**kwargs)
        self.entry = entry

    def compose(self) -> ComposeResult:
        text = Text()
        text.append(f"{self.entry.index:4d} ", style="dim")
        text.append(self.entry.command, style="cyan")
        yield Static(text)


class HistoryListView(ListView):
    """List view for history entries."""

    DEFAULT_CSS = """
    HistoryListView {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """


class HistoryWidget(Vertical):
    """
    History widget showing R command history.

    Features:
    - Display command history
    - Search/filter commands
    - Re-run previous commands
    - Copy commands to console
    """

    DEFAULT_CSS = """
    HistoryWidget {
        height: 100%;
        border: solid $secondary;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("enter", "run_selected", "Run", show=True),
        Binding("c", "copy_selected", "Copy", show=False),
        Binding("slash", "focus_search", "Search", show=True),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    class CommandSelected(Message):
        """Message sent when a command is selected to run."""

        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    def __init__(
        self,
        client: Optional[RSessionClient] = None,
        on_command_selected: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self._on_command_selected = on_command_selected
        self._header: Optional[HistoryHeader] = None
        self._search: Optional[HistorySearchInput] = None
        self._list_view: Optional[HistoryListView] = None
        self._all_entries: List[HistoryEntry] = []
        self._filtered_entries: List[HistoryEntry] = []

    def compose(self) -> ComposeResult:
        yield HistoryHeader()
        yield HistorySearchInput(on_filter=self._handle_filter)
        yield HistoryListView()

    def on_mount(self) -> None:
        self._header = self.query_one(HistoryHeader)
        self._search = self.query_one(HistorySearchInput)
        self._list_view = self.query_one(HistoryListView)

        # Load initial history
        if self.client:
            asyncio.create_task(self.refresh())
        else:
            self._load_demo_history()

    def _load_demo_history(self) -> None:
        """Load demo history for testing."""
        demo_commands = [
            "library(ggplot2)",
            "data <- read.csv('data.csv')",
            "head(data)",
            "summary(data)",
            "plot(data$x, data$y)",
            "model <- lm(y ~ x, data = data)",
            "summary(model)",
            "ggplot(data, aes(x, y)) + geom_point()",
            "install.packages('dplyr')",
            "library(dplyr)",
            "data %>% filter(x > 0) %>% head()",
            "mean(data$x)",
            "sd(data$y)",
            "hist(data$x)",
            "?ggplot",
        ]

        self._all_entries = [
            HistoryEntry(index=i + 1, command=cmd, timestamp=datetime.now())
            for i, cmd in enumerate(demo_commands)
        ]
        self._filtered_entries = self._all_entries.copy()
        self._update_list()

    async def refresh(self) -> None:
        """Refresh history from rsession."""
        if not self.client:
            return

        try:
            response = await self.client.get_console_history(max_items=500)
            if response.success and response.result:
                entries = []
                for i, item in enumerate(response.result):
                    if isinstance(item, str):
                        cmd = item
                    else:
                        cmd = item.get("command", "")

                    entry = HistoryEntry(
                        index=i + 1,
                        command=cmd,
                    )
                    entries.append(entry)

                self._all_entries = entries
                self._filtered_entries = entries.copy()
                self._update_list()
        except Exception as e:
            self.notify(f"History refresh error: {e}", severity="error")

    def _update_list(self) -> None:
        """Update the list view with current entries."""
        if not self._list_view:
            return

        # Clear and repopulate
        self._list_view.clear()

        for entry in reversed(self._filtered_entries):  # Show most recent first
            item = HistoryItem(entry)
            self._list_view.append(item)

        if self._header:
            self._header.set_count(len(self._filtered_entries))

    def _handle_filter(self, query: str) -> None:
        """Filter history based on search query."""
        query = query.lower().strip()

        if not query:
            self._filtered_entries = self._all_entries.copy()
        else:
            self._filtered_entries = [
                entry for entry in self._all_entries if query in entry.command.lower()
            ]

        self._update_list()

    def _get_selected_entry(self) -> Optional[HistoryEntry]:
        """Get the currently selected history entry."""
        if not self._list_view or self._list_view.index is None:
            return None

        # Get the highlighted item
        try:
            item = self._list_view.children[self._list_view.index]
            if isinstance(item, HistoryItem):
                return item.entry
        except (IndexError, AttributeError):
            pass

        return None

    async def action_refresh(self) -> None:
        """Refresh action handler."""
        await self.refresh()
        self.notify("History refreshed")

    async def action_run_selected(self) -> None:
        """Run the selected command."""
        entry = self._get_selected_entry()
        if entry:
            self.post_message(self.CommandSelected(entry.command))
            if self._on_command_selected:
                self._on_command_selected(entry.command)

    async def action_copy_selected(self) -> None:
        """Copy the selected command."""
        entry = self._get_selected_entry()
        if entry:
            # Note: Clipboard access is limited in terminal
            self.notify(f"Command: {entry.command[:50]}...")

    async def action_focus_search(self) -> None:
        """Focus the search input."""
        if self._search:
            self._search.focus()

    async def action_clear_search(self) -> None:
        """Clear the search filter."""
        if self._search:
            self._search.value = ""
            self._handle_filter("")

    def add_command(self, command: str) -> None:
        """Add a new command to the history."""
        new_index = len(self._all_entries) + 1
        entry = HistoryEntry(
            index=new_index,
            command=command,
            timestamp=datetime.now(),
        )
        self._all_entries.append(entry)
        self._filtered_entries = self._all_entries.copy()
        self._update_list()
