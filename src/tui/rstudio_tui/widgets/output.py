"""
Output Widget

Displays various output types:
- R output/errors
- Plots (as ASCII art or file references)
- Messages/warnings
- Build output
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane


class OutputType(Enum):
    """Types of output."""

    OUTPUT = "output"
    ERROR = "error"
    WARNING = "warning"
    MESSAGE = "message"
    PLOT = "plot"
    BUILD = "build"


@dataclass
class OutputEntry:
    """A single output entry."""

    type: OutputType
    content: str
    timestamp: datetime
    source: str = ""


class OutputLine(Static):
    """A single line of output."""

    DEFAULT_CSS = """
    OutputLine {
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, entry: OutputEntry, **kwargs):
        super().__init__(**kwargs)
        self.entry = entry

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        text = Text()

        # Timestamp (dim)
        time_str = self.entry.timestamp.strftime("%H:%M:%S")
        text.append(f"[{time_str}] ", style="dim")

        # Type indicator
        type_styles = {
            OutputType.OUTPUT: ("", "white"),
            OutputType.ERROR: ("[ERR] ", "bold red"),
            OutputType.WARNING: ("[WRN] ", "yellow"),
            OutputType.MESSAGE: ("[MSG] ", "cyan"),
            OutputType.PLOT: ("[PLT] ", "magenta"),
            OutputType.BUILD: ("[BLD] ", "green"),
        }

        prefix, style = type_styles.get(self.entry.type, ("", "white"))
        if prefix:
            text.append(prefix, style=style)

        # Content
        text.append(self.entry.content, style=style if self.entry.type == OutputType.ERROR else "")

        self.update(text)


class OutputPane(VerticalScroll):
    """Scrollable pane for output entries."""

    DEFAULT_CSS = """
    OutputPane {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._entries: List[OutputEntry] = []

    def add_entry(self, entry: OutputEntry) -> None:
        """Add a new output entry."""
        self._entries.append(entry)
        line = OutputLine(entry)
        self.mount(line)
        self.scroll_end()

    def clear_entries(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        self.remove_children()


class PlotsPane(Vertical):
    """Pane for displaying plots."""

    DEFAULT_CSS = """
    PlotsPane {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._plot_paths: List[str] = []
        self._current_index: int = -1

    def compose(self) -> ComposeResult:
        yield Static("No plots yet.\n\nPlots will appear here when created.", id="plot-display")
        yield Static("", id="plot-nav", classes="plot-nav")

    def add_plot(self, path: str) -> None:
        """Add a new plot."""
        self._plot_paths.append(path)
        self._current_index = len(self._plot_paths) - 1
        self._update_display()

    def _update_display(self) -> None:
        """Update the plot display."""
        display = self.query_one("#plot-display", Static)
        nav = self.query_one("#plot-nav", Static)

        if not self._plot_paths:
            display.update("No plots yet.\n\nPlots will appear here when created.")
            nav.update("")
        else:
            path = self._plot_paths[self._current_index]
            display.update(
                f"Plot saved to:\n{path}\n\n"
                f"(TUI cannot display images directly.\n"
                f"Use a file browser to view the plot.)"
            )
            nav.update(f"Plot {self._current_index + 1} of {len(self._plot_paths)} | ←/→ to navigate")

    def next_plot(self) -> None:
        """Show the next plot."""
        if self._plot_paths and self._current_index < len(self._plot_paths) - 1:
            self._current_index += 1
            self._update_display()

    def prev_plot(self) -> None:
        """Show the previous plot."""
        if self._plot_paths and self._current_index > 0:
            self._current_index -= 1
            self._update_display()


class OutputWidget(Vertical):
    """
    Output widget showing R output, errors, and plots.

    Features:
    - Tabbed interface for different output types
    - Output/errors from R
    - Plot references
    - Build output
    """

    DEFAULT_CSS = """
    OutputWidget {
        height: 100%;
        border: solid $secondary;
    }

    OutputWidget .output-header {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    OutputWidget TabbedContent {
        height: 1fr;
    }

    OutputWidget TabPane {
        padding: 0;
    }

    OutputWidget .plot-nav {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("c", "clear", "Clear", show=True),
        Binding("left", "prev_plot", "Prev Plot", show=False),
        Binding("right", "next_plot", "Next Plot", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._output_pane: Optional[OutputPane] = None
        self._plots_pane: Optional[PlotsPane] = None

    def compose(self) -> ComposeResult:
        yield Static("Output", classes="output-header")
        with TabbedContent():
            with TabPane("Output", id="output-tab"):
                yield OutputPane()
            with TabPane("Plots", id="plots-tab"):
                yield PlotsPane()

    def on_mount(self) -> None:
        self._output_pane = self.query_one(OutputPane)
        self._plots_pane = self.query_one(PlotsPane)

    def write_output(self, text: str, source: str = "") -> None:
        """Write regular output."""
        self._add_entry(OutputType.OUTPUT, text, source)

    def write_error(self, text: str, source: str = "") -> None:
        """Write error output."""
        self._add_entry(OutputType.ERROR, text, source)

    def write_warning(self, text: str, source: str = "") -> None:
        """Write warning output."""
        self._add_entry(OutputType.WARNING, text, source)

    def write_message(self, text: str, source: str = "") -> None:
        """Write message output."""
        self._add_entry(OutputType.MESSAGE, text, source)

    def write_build(self, text: str, source: str = "") -> None:
        """Write build output."""
        self._add_entry(OutputType.BUILD, text, source)

    def _add_entry(self, output_type: OutputType, content: str, source: str) -> None:
        """Add an output entry."""
        if self._output_pane:
            entry = OutputEntry(
                type=output_type,
                content=content,
                timestamp=datetime.now(),
                source=source,
            )
            self._output_pane.add_entry(entry)

    def add_plot(self, path: str) -> None:
        """Add a plot reference."""
        if self._plots_pane:
            self._plots_pane.add_plot(path)

    async def action_clear(self) -> None:
        """Clear all output."""
        if self._output_pane:
            self._output_pane.clear_entries()
        self.notify("Output cleared")

    async def action_prev_plot(self) -> None:
        """Show previous plot."""
        if self._plots_pane:
            self._plots_pane.prev_plot()

    async def action_next_plot(self) -> None:
        """Show next plot."""
        if self._plots_pane:
            self._plots_pane.next_plot()
